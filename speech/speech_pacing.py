"""Natural boundaries between independently synthesized speech segments."""
from __future__ import annotations

import numpy as np


class SpeechPacing:
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self._completed_at = None
        self._tail = 0.0
        self._pause = 0.0

    def _quiet_edge(self, chunks, *, trailing=False):
        samples = 0
        for chunk in reversed(chunks) if trailing else chunks:
            audio = chunk[::-1] if trailing else chunk
            voiced = np.flatnonzero(np.abs(audio) > .0001)
            samples += int(voiced[0]) if len(voiced) else len(audio)
            if len(voiced):
                break
        return samples / self.sample_rate

    def completed(self, text, chunks, *, now):
        self._completed_at = now
        self._tail = self._quiet_edge(chunks, trailing=True)
        ending = text.rstrip().rstrip('\"\'”’）)]」』')
        self._pause = (.55 if ending.endswith(('...', '…')) else
                       .4 if ending.endswith(('.', '!', '?', '。', '！', '？')) else .18)

    def delay(self, chunks, *, now):
        if self._completed_at is None:
            return 0.0
        # Count existing TTS silence and time spent waiting for the next segment.
        # A slow synthesis already provides a pause; never add another on top.
        quiet = self._tail + self._quiet_edge(chunks) + max(0, now - self._completed_at)
        return max(0.0, self._pause - quiet)

    def smooth(self, chunks):
        # Tiny edge ramps avoid a discontinuity if a provider returns nonzero
        # boundary samples. Keep all phonemes, samples and speaking speed intact.
        audio = np.concatenate(chunks).astype(np.float32)
        ramp = min(round(self.sample_rate * .008), len(audio) // 2)
        if ramp:
            gain = np.linspace(0, 1, ramp, dtype=np.float32)
            audio[:ramp] *= gain
            audio[-ramp:] *= gain[::-1]
        offsets = np.cumsum([0] + [len(chunk) for chunk in chunks])
        return [audio[start:end] for start, end in zip(offsets, offsets[1:])]
