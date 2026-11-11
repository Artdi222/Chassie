"""Local, opt-in ArcFace templates; recognition is a visual hint, not authentication."""
from pathlib import Path
import re

import numpy as np

MODEL_DIR = Path(__file__).parent / '.chassie' / 'vision-models'
DETECTOR = 'face_detection_yunet_2023mar.onnx'
RECOGNIZER = 'w600k_r50.onnx'
TEMPLATE_MODEL = 'arcface-w600k-r50'
TEMPLATE_SIZE = 512
# ArcFace's canonical 112x112 positions for eyes, nose tip and mouth corners.
ARCFACE_POINTS = ((38.2946, 51.6963), (73.5318, 51.5014), (56.0252, 71.7366),
                  (41.5493, 92.3655), (70.7299, 92.2041))

# A command must start the message (after an optional greeting/please), so
# questions that merely quote a command never enroll anyone.
_LEAD = r'(?:(?:hey|hi|hai|halo)\s+)?(?:chassie\s*[,!]?\s+)?(?:(?:tolong|please|coba|can you|could you|bisa(?:kah)?)\s+)?'
_SELF = r'(?:\s*ku|\s+(?:aku|saya|gue|gw))?'
_TAIL = r'(?:\s*,?\s*(?:ya|yah|dong|ok(?:e|ay)?|please|pls|thanks|makasih))*\s*[.!?]*'
_NAME = r'([^\W\d_][\w .\'-]{0,99}?)'
_COMMANDS = (
    ('remember', re.compile(_LEAD + r'(?:ingat(?:lah|in)?|inget(?:in)?|simpan|hafalkan|kenali|remember|save|learn)\s+'
                            r'(?:wajah|muka|my face|face)' + _SELF + r'(?:\s+(?:ya|dong))?'
                            # The name is optional: without one, Chassie enrolls the selected owner.
                            r'(?:\s*[,:-]?\s*(?:sebagai|as|dengan nama|nama\s*(?:ku|aku|saya|gue|gw)(?:\s+(?:adalah|tuh))?|'
                            r"aku|saya|gue|gw|i am|i'm|im|my name is|called)\s+" + _NAME + r')?' + _TAIL, re.IGNORECASE)),
    ('forget', re.compile(_LEAD + r'(?:lupakan|hapus|forget|delete)\s+(?:wajah|muka|the face of|face of|face)'
                          r'(?:\s+(?:milik|punya|of))?\s+' + _NAME + _TAIL, re.IGNORECASE)),
)


def face_command(text):
    """Only explicit whole-message enrollment/deletion requests mutate templates."""
    for action, pattern in _COMMANDS:
        match = pattern.fullmatch(text.strip())
        if match:
            return action, (match[1] or '').strip(" .'-")
    return None


def match_template(feature, templates, threshold=.35, margin=.08):
    """Conservative cosine match with an ambiguity gap; no speaker attribution."""
    feature = np.asarray(feature, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(feature)
    if feature.size != TEMPLATE_SIZE or not np.isfinite(feature).all() or norm < 1e-6:
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
                self.recognizer = cv2.dnn.readNetFromONNX(str(model_dir / RECOGNIZER))
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
            feature = self.embed(frame, face)
            matches.append(match_template(feature, templates))
            if len(faces) == 1:
                candidate = feature.tolist()
        return matches, candidate

    def embed(self, frame, face):
        """Align YuNet's five landmarks to ArcFace's template and return a unit embedding."""
        cv2 = self.cv2
        points = np.asarray(face[4:14], dtype=np.float32).reshape(5, 2)
        matrix, _ = cv2.estimateAffinePartial2D(points, np.asarray(ARCFACE_POINTS, dtype=np.float32), method=cv2.LMEDS)
        crop = cv2.warpAffine(frame, matrix, (112, 112))
        self.recognizer.setInput(cv2.dnn.blobFromImage(crop, 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True))
        feature = self.recognizer.forward().reshape(-1)
        return feature / max(float(np.linalg.norm(feature)), 1e-12)

    def close(self):
        if self.fallback is not None:
            self.fallback.close()
