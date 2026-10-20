"""Local, opt-in SFace templates; recognition is a visual hint, not authentication."""
from pathlib import Path
import re

import numpy as np

MODEL_DIR = Path(__file__).parent / '.chassie' / 'vision-models'
DETECTOR = 'face_detection_yunet_2023mar.onnx'
RECOGNIZER = 'face_recognition_sface_2021dec.onnx'


def face_command(text):
    """Only explicit whole-message enrollment/deletion requests mutate templates."""
    for action, pattern in (
        ('remember', r'(?:ingat wajahku sebagai|remember my face as)\s+(.{1,100}?)'),
        ('forget', r'(?:lupakan wajah|forget the face of)\s+(.{1,100}?)'),
    ):
        match = re.fullmatch(pattern + r'[.!]?', text.strip(), re.IGNORECASE)
        if match:
            return action, match[1].strip()
    return None


def match_template(feature, templates, threshold=.5, margin=.08):
    """Conservative cosine match with an ambiguity gap; no speaker attribution."""
    feature = np.asarray(feature, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(feature)
    if feature.size != 128 or not np.isfinite(feature).all() or norm < 1e-6:
        return None
    scores = []
    for item in templates:
        reference = np.asarray(item['embedding'], dtype=np.float32)
        denominator = norm * np.linalg.norm(reference)
        if denominator > 1e-6:
            scores.append((float(np.dot(feature, reference) / denominator), item))
    scores.sort(key=lambda pair: pair[0], reverse=True)
    if not scores or scores[0][0] < threshold:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
        return None
    score, item = scores[0]
    return {'profile_id': item['profile_id'], 'name': item['name'], 'similarity': round(score, 3)}


class FaceIdentity:
    def __init__(self, model_dir=MODEL_DIR):
        import cv2
        self.cv2 = cv2
        model_dir = Path(model_dir)
        self.detector = self.recognizer = self.fallback = None
        self.error = None
        try:
            if (model_dir / DETECTOR).is_file():
                self.detector = cv2.FaceDetectorYN.create(str(model_dir / DETECTOR), '', (640, 480), .9, .3, 100)
        except cv2.error:
            pass
        if self.detector is None:
            # Presence protection must survive missing identity-model weights.
            # Reuse the presence model shipped by the existing FaceTracker.
            import mediapipe as mp
            self._mp = mp
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(Path(__file__).parent / 'face_landmarker.task')),
                running_mode=mp.tasks.vision.RunningMode.IMAGE, num_faces=8)
            self.fallback = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        try:
            if self.detector is not None and (model_dir / RECOGNIZER).is_file():
                self.recognizer = cv2.FaceRecognizerSF.create(str(model_dir / RECOGNIZER), '')
        except cv2.error:
            pass
        if self.recognizer is None:
            self.error = 'Face recognition unavailable. Run scripts/install_vision.py; camera presence remains active.'

    @property
    def ready(self):
        return self.recognizer is not None

    def observe(self, frame, templates):
        height, width = frame.shape[:2]
        if self.fallback is not None:
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                   data=self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB))
            result = self.fallback.detect(image)
            return [None] * len(result.face_landmarks), None
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        if faces is None:
            return [], None
        if self.recognizer is None:
            return [None] * len(faces), None
        matches, candidate = [], None
        for face in faces[:8]:
            if min(face[2:4]) < 80:
                matches.append(None)
                continue
            aligned = self.recognizer.alignCrop(frame, face)
            feature = self.recognizer.feature(aligned).reshape(-1)
            matches.append(match_template(feature, templates))
            if len(faces) == 1:
                candidate = feature.tolist()
        return matches, candidate

    def close(self):
        if self.fallback is not None:
            self.fallback.close()
