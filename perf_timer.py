"""
perf_timer.py — Performance timing utility.

Tracks timestamps for various pipeline stages and produces
a formatted latency breakdown summary.
"""

import time


class PerfTimer:
    """Simple performance timer that records named marks and computes durations."""

    def __init__(self):
        self._marks: dict[str, float] = {}

    def mark(self, label: str):
        """Record a timestamp for the given label."""
        self._marks[label] = time.perf_counter()

    def has(self, label: str) -> bool:
        """Check if a mark exists."""
        return label in self._marks

    def elapsed(self, start: str, end: str) -> float:
        """
        Get duration in seconds between two marks.

        Returns 0.0 if either mark doesn't exist.
        """
        if start not in self._marks or end not in self._marks:
            return 0.0
        return self._marks[end] - self._marks[start]

    def since(self, label: str) -> float:
        """Get seconds elapsed since a mark was recorded."""
        if label not in self._marks:
            return 0.0
        return time.perf_counter() - self._marks[label]

    def summary(self) -> str:
        """
        Format a latency breakdown string.

        Expected marks: hermes_start, hermes_end, tts_start, tts_first_chunk, tts_end
        """
        parts = []

        hermes_time = self.elapsed("hermes_start", "hermes_end")
        if hermes_time > 0:
            parts.append(f"Hermes: {hermes_time:.2f}s")

        tts_first = self.elapsed("tts_start", "tts_first_chunk")
        if tts_first > 0:
            parts.append(f"TTS first chunk: {tts_first:.2f}s")

        tts_full = self.elapsed("tts_start", "tts_end")
        if tts_full > 0:
            parts.append(f"TTS full: {tts_full:.2f}s")

        # Total from hermes_start to tts_first_chunk (user-perceived latency)
        total = self.elapsed("hermes_start", "tts_first_chunk")
        if total > 0:
            parts.insert(0, f"Total: {total:.2f}s")

        return " | ".join(parts) if parts else "No timing data"

    def reset(self):
        """Clear all marks."""
        self._marks.clear()
