"""
audio_analyzer.py — Real-time amplitude extraction for lip-sync.

Processes audio chunks from streaming TTS and calculates normalized
mouth-open values using RMS with exponential smoothing.
"""

import numpy as np


class AudioAnalyzer:
    """Analyzes audio chunks to produce mouth-open values for lip-sync."""

    def __init__(self, sample_rate: int = 24000, chunk_ms: int = 50, smoothing: float = 0.3, threshold: float = 0.08, exponent: float = 0.8):
        """
        Args:
            sample_rate: Audio sample rate in Hz.
            chunk_ms: Expected chunk duration in milliseconds.
            smoothing: Exponential smoothing factor (0.0 = no smoothing, 1.0 = full smoothing).
            threshold: Noise gate threshold for closing the mouth fully.
            exponent: Exponent for increasing dynamic mouth movement contrast.
        """
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.smoothing = smoothing
        self.threshold = threshold
        self.exponent = exponent
        self._prev_value = 0.0
        self._max_rms = 0.01  # Adaptive max for normalization

    def analyze_chunk(self, audio_chunk: np.ndarray) -> float:
        """
        Analyze an audio chunk and return a mouth-open value.

        Args:
            audio_chunk: Numpy array of audio samples (float32 or int16).

        Returns:
            Mouth-open value between 0.0 (closed) and 1.0 (fully open).
        """
        if audio_chunk is None or len(audio_chunk) == 0:
            return 0.0

        # Convert to float if needed
        if audio_chunk.dtype == np.int16:
            samples = audio_chunk.astype(np.float32) / 32768.0
        else:
            samples = audio_chunk.astype(np.float32)

        # Calculate RMS
        rms = np.sqrt(np.mean(samples ** 2))

        # Update adaptive max
        if rms > self._max_rms:
            self._max_rms = rms
        else:
            # Slowly decay max to adapt to quieter speech
            self._max_rms = self._max_rms * 0.999 + rms * 0.001

        # Normalize to 0.0-1.0
        if self._max_rms > 0:
            normalized = min(rms / self._max_rms, 1.0)
        else:
            normalized = 0.0

        # Apply noise gate to allow mouth to close fully on quiet consonants
        if normalized < self.threshold:
            normalized = 0.0
        else:
            # Rescale remaining range to 0.0-1.0
            normalized = (normalized - self.threshold) / (1.0 - self.threshold)

        # Apply non-linear scaling to increase mouth movement contrast
        normalized = normalized ** self.exponent

        # Apply exponential smoothing to avoid jitter
        smoothed = self._prev_value * self.smoothing + normalized * (1.0 - self.smoothing)
        self._prev_value = smoothed

        # NumPy 2 keeps scalar arithmetic in float32. Avatar events cross JSON
        # and Qt boundaries, which require a native Python number.
        return float(smoothed)

    def reset(self):
        """Reset analyzer state between utterances."""
        self._prev_value = 0.0
        self._max_rms = 0.01
