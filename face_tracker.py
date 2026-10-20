"""Fresh, anonymous camera observations; no face identity or speaker attribution.

OpenCV and MediaPipe are optional and imported only by the camera worker.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger('face_tracker')
_MODEL_PATH = Path(__file__).parent / 'face_landmarker.task'


class FaceTracker:
    def __init__(self, config, *, clock=time.monotonic):
        cfg = config.get('face_tracker', {})
        self._enabled = cfg.get('enabled', False)
        self._camera_index = cfg.get('camera_index', 0)
        self._detection_confidence = cfg.get('detection_confidence', .5)
        self._update_interval = max(.05, float(cfg.get('update_interval', .2)))
        self._freshness = max(.1, float(cfg.get('freshness_seconds', 1.0)))
        self._max_faces = min(3, max(2, int(cfg.get('max_faces', 3))))
        self._clock = clock
        self._expressions = cfg.get('expressions', {})
        self._running = False
        self._thread = None
        self._cap = None
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._observation = self._empty(0.0)
        self.error = None

    @staticmethod
    def _empty(observed_at):
        return dict(available=False, face_count=0, observed_at=observed_at,
                    expression='unknown', identity_verified=False)

    def _invalidate(self):
        with self._lock:
            self._observation = self._empty(self._clock())

    def _record_result(self, result, captured_at):
        """Accept a detection stamped when capture completed, before inference.

        The timestamp measures application acquisition, not camera exposure time.
        A delayed result therefore expires rather than refreshing stale context.
        """
        count = len(result.face_landmarks or [])
        expression = 'unknown'
        if count == 1 and result.face_blendshapes:
            expression = self._classify_from_blendshapes(result.face_blendshapes[0])
        with self._lock:
            if captured_at < self._observation['observed_at']:
                return
            self._observation = dict(available=count > 0, face_count=count,
                                     observed_at=captured_at, expression=expression,
                                     identity_verified=False)

    def get_observation(self):
        with self._lock:
            observation = dict(self._observation)
        age = self._clock() - observation['observed_at']
        if not observation['available'] or age < 0 or age > self._freshness:
            return self._empty(observation['observed_at'])
        return observation

    def get_current_expression(self):
        return self.get_observation()['expression']

    def get_context_string(self):
        observation = self.get_observation()
        if not observation['available']:
            return ''
        count = observation['face_count']
        if count > 1:
            return f'Camera observes {count} faces; identities and active speaker are unknown.'
        descriptions = {
            'smiling': 'a smile-like mouth shape',
            'smiling_mouth_open': 'a smile-like mouth shape with mouth open',
            'brows_lowered': 'lowered brows',
            'eyes_wide': 'widened eyes and raised inner brows',
            'eyes_closed': 'closed eyes',
        }
        description = descriptions.get(observation['expression'])
        if description is None:
            return ''
        return f'One unidentified face shows {description}; this does not establish emotion or speaker identity.'

    def start(self):
        if not self._enabled or self._running:
            return
        if self._thread and self._thread.is_alive():
            return
        if not _MODEL_PATH.is_file():
            self.error = 'Face model unavailable; install face_landmarker.task to enable camera observations.'
            logger.warning(self.error)
            self._invalidate()
            return
        self._wake.clear()
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, name='face-tracker', daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._wake.set()
        self._invalidate()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        # Camera worker owns release; avoid releasing an OpenCV capture object
        # concurrently with its native read call after a join timeout.

    def _capture_loop(self):
        cap = landmarker = None
        try:
            import os
            import cv2
            import mediapipe as mp

            backend = cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY
            cap = cv2.VideoCapture(self._camera_index, backend)
            if not cap.isOpened() and backend == cv2.CAP_DSHOW:
                cap.release()
                cap = cv2.VideoCapture(self._camera_index, cv2.CAP_ANY)
            self._cap = cap
            if not cap.isOpened():
                raise RuntimeError('Camera could not be opened')
            # Best effort: backend support varies. Small frames constrain CPU load.
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(_MODEL_PATH)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_faces=self._max_faces,
                min_face_detection_confidence=self._detection_confidence,
                min_face_presence_confidence=self._detection_confidence,
                min_tracking_confidence=self._detection_confidence,
                output_face_blendshapes=True,
            )
            landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
            last_timestamp = -1
            while self._running:
                okay, frame = cap.read()
                captured_at = self._clock()
                if not self._running:
                    break
                if not okay:
                    self.error = 'Camera frame unavailable'
                    self._invalidate()
                    self._wake.wait(.5)
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp = max(last_timestamp + 1, int(captured_at * 1000))
                last_timestamp = timestamp
                result = landmarker.detect_for_video(image, timestamp)
                if self._running:
                    self._record_result(result, captured_at)
                    self.error = None
                self._wake.wait(self._update_interval)
        except Exception as exc:
            self.error = f'Camera observations unavailable ({type(exc).__name__})'
            logger.warning(self.error)
        finally:
            self._running = False
            self._invalidate()
            try:
                if landmarker is not None:
                    landmarker.close()
            finally:
                if cap is not None:
                    cap.release()
                self._cap = None

    def _classify_from_blendshapes(self, blendshapes):
        scores = {item.category_name: item.score for item in blendshapes}
        def average(*names):
            return sum(scores.get(name, 0) for name in names) / len(names)
        smile = average('mouthSmileLeft', 'mouthSmileRight')
        if smile > self._expressions.get('smile_threshold', .6):
            return 'smiling_mouth_open' if scores.get('jawOpen', 0) > .3 else 'smiling'
        if average('browInnerUp', 'eyeWideLeft', 'eyeWideRight') > self._expressions.get('surprise_threshold', .7):
            return 'eyes_wide'
        if average('browDownLeft', 'browDownRight') > self._expressions.get('frown_threshold', .4):
            return 'brows_lowered'
        if average('eyeBlinkLeft', 'eyeBlinkRight') > .8:
            return 'eyes_closed'
        return 'neutral'
