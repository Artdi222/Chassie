"""Optional GPU acceleration for the AppImage (CPU-only inside): the CUDA build of ONNX Runtime and NVIDIA's
CUDA/cuDNN libraries, about 3 GB, installed into DATA/gpu. start.py puts that folder first on sys.path, where
faster-whisper and ONNX Runtime find the libraries the same way a git install does.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

from paths import DATA

FOLDER = DATA / 'gpu'
# No dependencies: numpy and friends stay the AppImage's own. Same versions as requirements.txt.
PACKAGES = ['onnxruntime-gpu==1.26.0', 'nvidia-cublas-cu12~=12.0', 'nvidia-cuda-runtime-cu12~=12.0',
            'nvidia-cuda-nvrtc-cu12~=12.0', 'nvidia-cufft-cu12~=11.0', 'nvidia-curand-cu12~=10.0',
            'nvidia-nvjitlink-cu12~=12.0', 'nvidia-cudnn-cu12~=9.0']


def nvidia_present():
    return Path('/proc/driver/nvidia/version').is_file() or bool(shutil.which('nvidia-smi'))


def cuda_active():
    try:
        import onnxruntime
        return 'CUDAExecutionProvider' in onnxruntime.get_available_providers()
    except ImportError: return False


def install():
    """Download into a scratch folder, then swap it in: a half download is never used."""
    pending = FOLDER.with_name('gpu.partial')
    shutil.rmtree(pending, ignore_errors=True)
    done = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-cache-dir', '--disable-pip-version-check',
                           '--target', str(pending), *PACKAGES], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3600)
    if done.returncode:
        shutil.rmtree(pending, ignore_errors=True)
        raise RuntimeError('GPU acceleration could not be downloaded: ' + ((done.stderr or done.stdout).strip().splitlines() or ['pip failed'])[-1][:200])
    shutil.rmtree(FOLDER, ignore_errors=True)
    pending.replace(FOLDER)
