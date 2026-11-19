"""ONNX Runtime sessions that use the laptop GPU when possible, CPU otherwise.

The CUDA/cuDNN libraries come from the nvidia-* pip packages already used by
faster-whisper. Each session caps its own GPU arena so Whisper and VOICEVOX keep room.
"""
from __future__ import annotations

import logging

logger = logging.getLogger('onnx')
_preloaded = None


def _preload(ort):
    global _preloaded
    if _preloaded is None:
        try:
            ort.preload_dlls(cuda=True, cudnn=True, msvc=False)
            _preloaded = True
        except Exception as exc:  # Missing pip CUDA libs: ORT falls back to CPU below.
            logger.info('CUDA libraries not preloaded: %s', exc)
            _preloaded = False
    return _preloaded


def gpu_available():
    import onnxruntime as ort
    return 'CUDAExecutionProvider' in ort.get_available_providers() and _preload(ort)


def create_session(path, *, prefer_gpu=True, gpu_mem_mb=512, threads=2):
    """Return (session, on_gpu). Never raises just because CUDA is unusable."""
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads  # Leave CPU for VOICEVOX and Whisper fallback.
    options.inter_op_num_threads = 1
    options.log_severity_level = 3
    if prefer_gpu and gpu_available():
        cuda = ('CUDAExecutionProvider', {'device_id': 0, 'arena_extend_strategy': 'kSameAsRequested',
                                          'gpu_mem_limit': gpu_mem_mb * 1024 * 1024})
        try:
            session = ort.InferenceSession(str(path), options, providers=[cuda, 'CPUExecutionProvider'])
            if session.get_providers()[0] == 'CUDAExecutionProvider':
                return session, True
        except Exception as exc:
            logger.warning('GPU session failed for %s, using CPU: %s', path, exc)
    return ort.InferenceSession(str(path), options, providers=['CPUExecutionProvider']), False
