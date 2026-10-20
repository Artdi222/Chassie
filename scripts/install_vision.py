"""Install hash-checked OpenCV Zoo face models into Chassie's local cache."""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    'face_detection_yunet': ('face_detection_yunet_2023mar.onnx', '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'),
    'face_recognition_sface': ('face_recognition_sface_2021dec.onnx', '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79'),
}


def install():
    target = ROOT / '.chassie' / 'vision-models'
    target.mkdir(parents=True, exist_ok=True)
    for folder, (name, digest) in MODELS.items():
        path = target / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            print(f'Ready: {name}', flush=True)
            continue
        url = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{folder}/{name}'
        pending = path.with_suffix('.download')
        try:
            with urllib.request.urlopen(url, timeout=60) as response, pending.open('wb') as output:
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > 45_000_000:
                        raise RuntimeError('Model download exceeds expected size')
                    output.write(block)
            if hashlib.sha256(pending.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f'Model checksum mismatch: {name}')
            pending.replace(path)
            print(f'Installed: {name}', flush=True)
        finally:
            pending.unlink(missing_ok=True)
    # Retain the licenses beside the model weights.
    for folder in MODELS:
        path = target / (folder + '-LICENSE')
        if not path.exists():
            url = f'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/{folder}/LICENSE'
            with urllib.request.urlopen(url, timeout=30) as response:
                path.write_bytes(response.read(100_000))


if __name__ == '__main__':
    install()
