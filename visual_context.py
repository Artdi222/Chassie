"""Automatic local camera/screen snapshots, refreshed independently of chat windows.

Only the latest frame is held in RAM. Model requests receive a fresh snapshot;
capture workers never contact a model provider or write screenshots to disk.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import numpy as np

from face_identity import FaceIdentity, MODEL_DIR


def encode_frame(frame, max_edge=1600):
    import cv2
    height, width = frame.shape[:2]
    scale = min(1.0, max_edge / max(height, width))
    if scale < 1:
        frame = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    okay, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not okay or len(jpeg) > 2_000_000:
        raise RuntimeError('Visual snapshot could not be encoded within its size limit')
    return 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')


def capture_screen():
    """Capture the visible GUI, including app contents, on Wayland or X11."""
    import cv2
    import numpy as np
    title = ''
    if os.environ.get('WAYLAND_DISPLAY'):
        if not shutil.which('grim'):
            raise RuntimeError('Screen capture needs grim on this Wayland desktop')
        command = ['grim', '-t', 'png', '-']
        if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl'):
            try:
                active = json.loads(subprocess.check_output(['hyprctl', '-j', 'activewindow'], timeout=2))
                title = str(active.get('class', ''))[:100] + ' — ' + str(active.get('title', ''))[:300]
                monitors = json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors'], timeout=2))
                monitor = next((m for m in monitors if m['id'] == active.get('monitor')),
                               next((m for m in monitors if m.get('focused')), None))
                if monitor:
                    command = ['grim', '-o', monitor['name'], '-t', 'png', '-']
            except (OSError, subprocess.SubprocessError, ValueError, KeyError):
                pass
        raw = subprocess.check_output(command, timeout=4, stderr=subprocess.DEVNULL)
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    else:
        from PIL import ImageGrab
        frame = cv2.cvtColor(np.asarray(ImageGrab.grab(all_screens=True)), cv2.COLOR_RGB2BGR)
    if frame is None:
        raise RuntimeError('Desktop capture returned no image')
    return encode_frame(frame, 1920), title


class VisualContext:
    def __init__(self, config, memory, *, clock=time.monotonic):
        cfg = config.get('vision', {})
        self.camera_enabled = cfg.get('camera_enabled', False)
        self.screen_enabled = cfg.get('screen_enabled', False)
        self.camera_index = config.get('face_tracker', {}).get('camera_index', 0)
        self.interval = max(1.0, float(cfg.get('interval_seconds', 2)))
        self.freshness = max(self.interval * 2, 5.0)
        self.model_dir = Path(cfg.get('model_dir', MODEL_DIR))
        if not self.model_dir.is_absolute():
            self.model_dir = Path(__file__).parent / self.model_dir
        self.memory, self.clock = memory, clock
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._threads = []
        self._frames = {}
        # Recent single-face embeddings; enrollment averages the consistent ones.
        self._candidate = []
        self.enrollment_window = max(self.interval * 3, 6.0)
        self._identity = {'face_count': 0, 'matches': [], 'ready': False, 'error': None}
        self._identity_revision = -1
        self._errors = {'camera': None, 'screen': None}

    def start(self):
        if self._threads:
            return
        for enabled, target in ((self.camera_enabled, self._camera_loop), (self.screen_enabled, self._screen_loop)):
            if enabled:
                worker = threading.Thread(target=target, daemon=True, name='vision-' + target.__name__)
                self._threads.append(worker)
                worker.start()

    def _record(self, source, image, captured_at, title=''):
        with self._lock:
            if not self._stop.is_set():
                self._frames[source] = {'source': source, 'image_url': image, 'captured_at': captured_at, 'title': title}
                self._errors[source] = None

    def _fail(self, source, message):
        with self._lock:
            self._frames.pop(source, None)
            self._errors[source] = message
            if source == 'camera':
                self._candidate = []
                self._identity = {'face_count': 0, 'matches': [], 'ready': False, 'error': message}

    def _screen_loop(self):
        while not self._stop.is_set():
            try:
                captured_at = self.clock()
                image, title = capture_screen()
                self._record('screen', image, captured_at, title)
            except Exception as exc:
                self._fail('screen', f'Screen unavailable ({type(exc).__name__}). Check desktop capture access.')
            self._stop.wait(self.interval)

    def _camera_loop(self):
        import cv2
        recognizer = None
        recognition_error = None
        try:
            recognizer = FaceIdentity(self.model_dir)
            recognition_error = recognizer.error
        except Exception as exc:
            recognition_error = str(exc) if isinstance(exc, RuntimeError) else 'Face recognition unavailable'
        while not self._stop.is_set():
            cap = None
            try:
                cap = cv2.VideoCapture(self.camera_index)
                if not cap.isOpened():
                    raise RuntimeError('Camera cannot be opened')
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                last = -float('inf')
                while not self._stop.is_set():
                    okay, frame = cap.read()
                    if not okay:
                        raise RuntimeError('Camera returned no frame')
                    now = self.clock()
                    if now - last < self.interval:
                        self._stop.wait(.03)
                        continue
                    last = now
                    image = encode_frame(frame, 960)
                    matches, candidate = [], None
                    revision = self.memory.revision
                    if recognizer:
                        try:
                            matches, candidate = recognizer.observe(frame, self.memory.list_faces())
                            recognition_error = recognizer.error
                        except Exception:
                            # A recognizer failure must not disable visual camera input.
                            recognition_error = 'Face recognition unavailable for this frame.'
                    with self._lock:
                        if self._stop.is_set():
                            break
                        self._identity = {'face_count': len(matches), 'matches': [m for m in matches if m],
                                          'ready': recognizer is not None and recognizer.ready and not recognition_error,
                                          'presence_ready': recognizer is not None and not (recognition_error == 'Face recognition unavailable for this frame.'),
                                          'error': recognition_error}
                        self._identity_revision = revision
                        # Any frame without exactly one face restarts sampling, so two people never blend.
                        self._candidate = ([c for c in self._candidate if now - c[1] <= self.enrollment_window][-4:] + [(candidate, now)]) if candidate else []
                        self._record('camera', image, now)
            except Exception as exc:
                self._fail('camera', f'Camera unavailable ({type(exc).__name__}). Check camera connection and access.')
            finally:
                if cap is not None:
                    cap.release()
            self._stop.wait(3)
        if recognizer:
            recognizer.close()

    def snapshot(self):
        now = self.clock()
        with self._lock:
            return [dict(frame) for frame in self._frames.values() if now - frame['captured_at'] <= self.freshness]

    def request_context(self):
        # Images and participant observations belong to the same captured state.
        with self._lock:
            return self.snapshot(), self.status()

    def status(self):
        frames = {frame['source']: frame for frame in self.snapshot()}
        with self._lock:
            identity = dict(self._identity)
            if 'camera' not in frames or self._identity_revision != self.memory.revision:
                identity['matches'] = []
                if 'camera' not in frames:
                    identity['face_count'] = 0
            return {'camera': {'enabled': self.camera_enabled, 'available': 'camera' in frames, 'error': self._errors['camera']},
                    'screen': {'enabled': self.screen_enabled, 'available': 'screen' in frames, 'error': self._errors['screen']},
                    'identity': identity}

    def get_observation(self):
        status = self.status()
        return {'available': status['camera']['available'], 'face_count': status['identity']['face_count'],
                'expression': 'unknown', 'identity_verified': False, 'observed_at': self.clock()}

    def enrollment(self):
        with self._lock:
            now = self.clock()
            if not self._candidate or now - self._candidate[-1][1] > self.freshness:
                raise ValueError('Face not saved. Face the camera alone in good light, then repeat your request.')
            samples = [np.asarray(f, dtype=np.float32) for f, at in self._candidate if now - at <= self.enrollment_window]
        latest = samples[-1] / max(float(np.linalg.norm(samples[-1])), 1e-12)
        consistent = [f / n for f in samples if (n := float(np.linalg.norm(f))) > 1e-12 and float(np.dot(f / n, latest)) >= .5]
        mean = np.mean(consistent, axis=0)
        return (mean / max(float(np.linalg.norm(mean)), 1e-12)).astype(float).tolist()

    def stop(self):
        self._stop.set()
        for worker in self._threads:
            worker.join(timeout=5)
        with self._lock:
            self._frames.clear()
            self._candidate = []
            self._identity = {'face_count': 0, 'matches': [], 'ready': False, 'error': None}
