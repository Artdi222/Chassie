"""Install hash-checked face models (YuNet detector, ArcFace recognizer) into Chassie's local cache."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DETECTOR = ('face_detection_yunet', 'face_detection_yunet_2023mar.onnx',
            '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4')
# InsightFace publishes ArcFace only inside the buffalo_l pack; only w600k_r50 is kept.
ARCFACE_PACK = ('https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
                '80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f')
ARCFACE = ('w600k_r50.onnx', '4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43')
# Optional ambient object detector (COCO labels, Apache-2.0) used to notice new things in view.
OBJECTS = ('https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite',
           'efficientdet_lite0.tflite', '0720bf247bd76e6594ea28fa9c6f7c5242be774818997dbbeffc4da460c723bb')


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as file:
        while block := file.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def download(url, path, limit):
    pending = path.with_suffix('.download')
    try:
        with urllib.request.urlopen(url, timeout=60) as response, pending.open('wb') as output:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > limit:
                    raise RuntimeError('Model download exceeds expected size')
                output.write(block)
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def install():
    target = ROOT / '.chassie' / 'vision-models'
    target.mkdir(parents=True, exist_ok=True)
    folder, name, expected = DETECTOR
    path = target / name
    if path.exists() and digest(path) == expected:
        print(f'Ready: {name}', flush=True)
    else:
        download(f'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{folder}/{name}', path, 45_000_000)
        if digest(path) != expected:
            path.unlink()
            raise RuntimeError(f'Model checksum mismatch: {name}')
        print(f'Installed: {name}', flush=True)
    license_path = target / (folder + '-LICENSE')
    if not license_path.exists():
        url = f'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/{folder}/LICENSE'
        with urllib.request.urlopen(url, timeout=30) as response:
            license_path.write_bytes(response.read(100_000))

    url, name, expected = OBJECTS
    path = target / name
    if path.exists() and digest(path) == expected:
        print(f'Ready: {name}', flush=True)
    else:
        download(url, path, 10_000_000)
        if digest(path) != expected:
            path.unlink()
            raise RuntimeError(f'Model checksum mismatch: {name}')
        print(f'Installed: {name}', flush=True)

    name, expected = ARCFACE
    path = target / name
    if path.exists() and digest(path) == expected:
        print(f'Ready: {name}', flush=True)
        return
    url, pack_digest = ARCFACE_PACK
    pack = target / 'buffalo_l.zip'
    try:
        print('Downloading ArcFace (InsightFace buffalo_l, ~290 MB)...', flush=True)
        download(url, pack, 300_000_000)
        if digest(pack) != pack_digest:
            raise RuntimeError('Model checksum mismatch: buffalo_l.zip')
        with zipfile.ZipFile(pack) as archive:
            path.write_bytes(archive.read(name))
        if digest(path) != expected:
            path.unlink()
            raise RuntimeError(f'Model checksum mismatch: {name}')
        print(f'Installed: {name} (InsightFace weights: non-commercial research use)', flush=True)
    finally:
        pack.unlink(missing_ok=True)


def check_open_vocabulary():
    target = ROOT / '.chassie' / 'vision-models'
    if (target / 'yoloe-11s-pf-416.onnx').exists() and (target / 'yoloe-11s-pf.names.json').exists():
        print('Ready: yoloe-11s-pf-416.onnx', flush=True)
    else:
        print('Optional: build the more accurate open-vocabulary camera model with the uv command '
              'in scripts/export_yoloe.py; EfficientDet-Lite0 is used until then.', flush=True)


if __name__ == '__main__':
    install()
    check_open_vocabulary()
