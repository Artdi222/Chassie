"""Local ambient vision: notice objects that newly appear in the camera view.

Detection runs on the existing 2-second camera frames with a small COCO detector.
Only label names leave this module; Chassie decides later whether a snapshot is sent.
"""
from __future__ import annotations

from pathlib import Path

OBJECT_MODEL = 'efficientdet_lite0.tflite'
OPEN_MODEL = 'yoloe-11s-pf-416.onnx'
OPEN_NAMES = 'yoloe-11s-pf.names.json'
# Open-vocabulary tags that describe the owner, the room or the camera itself change
# with every movement; they are never worth a remark.
PERSONAL = frozenset({
    'man', 'woman', 'boy', 'girl', 'child', 'person', 'people', 'face', 'head', 'hair', 'eye', 'eyes',
    'nose', 'mouth', 'lip', 'ear', 'beard', 'hand', 'finger', 'arm', 'neck', 'shoulder', 'skin', 'smile',
    'shirt', 't-shirt', 'top', 'sweater', 'hoodie', 'jacket', 'coat', 'clothing', 'collar', 'sleeve',
    'glasses', 'eyeglasses', 'spectacles', 'headphones', 'earphone', 'room', 'wall', 'ceiling', 'floor',
    'door', 'window', 'curtain', 'light', 'lamp', 'lighting', 'indoor', 'home', 'bedroom', 'living room',
    'office', 'darkness', 'dark', 'night', 'shadow', 'selfie', 'portrait', 'photo', 'picture', 'image',
    'camera', 'webcam', 'screen', 'monitor', 'computer', 'desk', 'table', 'chair', 'bed', 'pillow',
    'blanket', 'sofa', 'couch', 'white', 'black', 'gray', 'grey', 'stand', 'sit', 'stare', 'look'})
# Always around a desk or too noisy to be worth a remark.
IGNORED = frozenset({'person', 'chair', 'couch', 'bed', 'dining table', 'tv', 'laptop',
                     'keyboard', 'mouse', 'remote', 'refrigerator', 'oven', 'sink', 'toilet'})


class SceneWatcher:
    """Report a label once it is seen in consecutive frames after a long absence.

    Labels visible during warm-up form the baseline room and are never reported.
    """

    def __init__(self, *, warmup=10.0, forget=180.0, confirm=2):
        self.warmup, self.forget, self.confirm = warmup, forget, confirm
        self.started = None
        self.last_seen = {}
        self.streak = {}
        self.reported = {}

    def feed(self, labels, now):
        if self.started is None:
            self.started = now
        labels = {label for label in labels if label not in IGNORED}
        new = []
        for label in labels:
            streak = self.streak.get(label, 0) + 1
            self.streak[label] = streak
            self.last_seen[label] = now
            if now - self.started < self.warmup:
                self.reported[label] = now
                continue
            if streak >= self.confirm and now - self.reported.get(label, -float('inf')) >= self.forget:
                self.reported[label] = now
                new.append(label)
        for label in list(self.streak):
            if label not in labels:
                self.streak[label] = 0
        return sorted(new)


class ChangeWatcher:
    """Detect a large view change that persists, e.g. something held up to the camera.

    The baseline is the last stable view. A change counts only when `confirm`
    consecutive frames differ from the baseline and agree with each other, so a
    person moving back and forth does not trigger it.
    """

    def __init__(self, *, threshold=22.0, confirm=2, cooldown=120.0, adapt=.1):
        self.threshold, self.confirm, self.cooldown, self.adapt = threshold, confirm, cooldown, adapt
        self.baseline = self.candidate = None
        self.streak = 0
        self.last_event = -float('inf')

    def _differs(self, a, b):
        import numpy as np
        return float(np.mean(np.abs(a - b))) >= self.threshold

    def feed(self, thumbnail, now):
        import numpy as np
        view = np.asarray(thumbnail, dtype=np.float32)
        if self.baseline is None or self.baseline.shape != view.shape:
            self.baseline, self.candidate, self.streak = view, None, 0
            return False
        if not self._differs(view, self.baseline):
            self.baseline += (view - self.baseline) * self.adapt  # Slow lighting drift.
            self.candidate, self.streak = None, 0
            return False
        consistent = self.candidate is not None and not self._differs(view, self.candidate)
        self.streak = self.streak + 1 if consistent else 1
        self.candidate = view
        if self.streak < self.confirm:
            return False
        self.baseline, self.candidate, self.streak = view, None, 0
        if now - self.last_event < self.cooldown:
            return False
        self.last_event = now
        return True


class OpenVocabularyDetector:
    """YOLOE-11s prompt-free (~4,600 everyday labels) on the GPU when available.

    The exported graph already reduces class scores to the best label per candidate,
    so only a few hundred KB leave the GPU per frame.
    """

    def __init__(self, model_dir, threshold=.35, *, prefer_gpu=True):
        import json
        from onnx_gpu import create_session
        model_dir = Path(model_dir)
        if not (model_dir / OPEN_MODEL).is_file():
            raise FileNotFoundError('Open-vocabulary model missing. Run scripts/install_vision.py.')
        self.names = json.loads((model_dir / OPEN_NAMES).read_text(encoding='utf-8'))
        self.session, self.on_gpu = create_session(model_dir / OPEN_MODEL, prefer_gpu=prefer_gpu, gpu_mem_mb=512)
        self.input = self.session.get_inputs()[0]
        self.size = int(self.input.shape[-1])
        self.threshold = threshold

    def _tensor(self, rgb_frame):
        import cv2
        import numpy as np
        h, w = rgb_frame.shape[:2]
        scale = self.size / max(h, w)
        resized = cv2.resize(rgb_frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        top, left = (self.size - resized.shape[0]) // 2, (self.size - resized.shape[1]) // 2
        canvas[top:top + resized.shape[0], left:left + resized.shape[1]] = resized
        return (canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255.0)

    def detections(self, rgb_frame):
        """[(label, score, area_fraction)] best first, one entry per label."""
        import numpy as np
        boxes, scores, classes = self.session.run(None, {self.input.name: self._tensor(rgb_frame)})
        scores, classes, boxes = scores[0], classes[0], boxes[0]
        keep = np.nonzero(scores >= self.threshold)[0]
        best = {}
        for index in keep[np.argsort(-scores[keep])][:40]:
            label = self.names[int(classes[index])]
            if label in best:
                continue
            area = float(boxes[2, index] * boxes[3, index]) / (self.size * self.size)
            best[label] = (label, float(scores[index]), round(area, 3))
        return list(best.values())

    def labels(self, rgb_frame):
        return {label for label, _, _ in self.detections(rgb_frame) if label not in PERSONAL}

    def close(self):
        self.session = None


def create_detector(model_dir):
    """Best available detector: open-vocabulary YOLOE, else EfficientDet-Lite0 (COCO)."""
    try:
        return OpenVocabularyDetector(model_dir)
    except FileNotFoundError:
        return ObjectDetector(model_dir)


class ObjectDetector:
    """MediaPipe EfficientDet-Lite0 on CPU (~30 ms per 640x480 frame)."""

    def __init__(self, model_dir, threshold=.4):
        path = Path(model_dir) / OBJECT_MODEL
        if not path.is_file():
            raise FileNotFoundError('Object model missing. Run scripts/install_vision.py.')
        import mediapipe as mp
        self._mp = mp
        options = mp.tasks.vision.ObjectDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE, max_results=8, score_threshold=threshold)
        self.detector = mp.tasks.vision.ObjectDetector.create_from_options(options)

    def labels(self, rgb_frame):
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.detector.detect(image)
        return {d.categories[0].category_name for d in result.detections if d.categories}

    def close(self):
        self.detector.close()
