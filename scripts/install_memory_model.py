"""Install the local multilingual embedding model used for semantic memory recall.

intfloat/multilingual-e5-small (MIT), ONNX export by Xenova, pinned revision and hashes.
fp16 runs on the GPU (CUDA); the int8 file is the CPU fallback.
"""
import hashlib
from pathlib import Path
import shutil

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.chassie' / 'memory-models' / 'multilingual-e5-small'
REPO = 'Xenova/multilingual-e5-small'
REVISION = '761b726dd34fb83930e26aab4e9ac3899aa1fa78'
FILES = {
    'onnx/model_fp16.onnx': '0e0fe349c99ea21c6f3aa273af21f7fb753c1e1174ef1647032029c2be3251c3',
    'onnx/model_quantized.onnx': 'f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193',
    'tokenizer.json': '0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39',
}


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as file:
        while block := file.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def install():
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        path = TARGET / Path(name).name
        if path.exists() and digest(path) == expected:
            print(f'Ready: {path.name}', flush=True)
            continue
        cached = Path(hf_hub_download(REPO, name, revision=REVISION))
        if digest(cached) != expected:
            raise RuntimeError(f'Checksum mismatch: {name}')
        shutil.copyfile(cached, path)
        print(f'Installed: {path.name}', flush=True)


if __name__ == '__main__':
    install()
