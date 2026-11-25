"""Keep one steady voice across moods: tidy spoken text and even out loudness per sentence.

VOICEVOX reads chat symbols literally (w -> "daburyuu", (笑) -> "warai") and renders
hesitant or excited lines up to ~9 dB quieter than calm ones, so a reply that changes
mood sounds like a different voice. Display text is never changed here.
"""
from __future__ import annotations

import re

import numpy as np

_DECOR = re.compile(r'[♪♫☆★♡♥❤✨💕😊😂🤣😅😳🥺💦✧･ﾟ]+')
_LAUGH = re.compile(r'[（(]\s*(?:笑|爆笑|汗|照)\s*[)）]')
_TRAILING_W = re.compile(r'(?<=[぀-ヿ一-鿿。、！？!?])[wWｗＷ]+(?=$|[\s。、！？!?])')
_ELLIPSIS = re.compile(r'(?:…|‥|\.{2,}|・{2,})+')
_WAVE = re.compile(r'[〜～]+')
_LONG = re.compile(r'ー{2,}')
_BANGS = re.compile(r'[！!]{2,}')
_MIXED = re.compile(r'[！!？?]*[？?][！!？?]*')

TARGET_DB = -20.0   # Loudness of voiced frames for every sentence (calm Normal speech is ~-20).
PEAK_DB = -1.5
MAX_GAIN_DB = 12.0


def clean_speech(text):
    """Speakable Japanese with the same meaning; falls back to the input if nothing is left."""
    cleaned = _LAUGH.sub('', text)
    cleaned = _DECOR.sub('', cleaned)
    cleaned = _TRAILING_W.sub('', cleaned)
    cleaned = _ELLIPSIS.sub('、', cleaned)
    cleaned = _WAVE.sub('ー', cleaned)
    cleaned = _LONG.sub('ー', cleaned)
    cleaned = _BANGS.sub('！', cleaned)
    cleaned = _MIXED.sub('？', cleaned)
    cleaned = re.sub(r'、{2,}', '、', cleaned)
    cleaned = re.sub(r'、(?=[。！？])', '', cleaned)
    cleaned = cleaned.strip(' 、')
    return cleaned if re.search(r'[぀-ヿ一-鿿]', cleaned) else text


def normalize_loudness(audio, sample_rate, *, target_db=TARGET_DB, peak_db=PEAK_DB):
    """Scale one sentence so its voiced frames sit at target_db, never clipping."""
    audio = np.asarray(audio, dtype=np.float32)
    frame = max(1, int(sample_rate * .02))
    usable = len(audio) // frame * frame
    if usable == 0:
        return audio
    frames = np.sqrt(np.mean(audio[:usable].reshape(-1, frame) ** 2, axis=1))
    loudest = float(frames.max())
    if loudest < 1e-5:
        return audio
    voiced = frames[frames >= loudest * 10 ** (-30 / 20)]  # Ignore pauses and breaths.
    level = float(np.sqrt(np.mean(voiced ** 2)))
    gain = min(10 ** ((target_db - 20 * np.log10(level)) / 20), 10 ** (MAX_GAIN_DB / 20))
    peak = float(np.abs(audio).max()) * gain
    ceiling = 10 ** (peak_db / 20)
    if peak > ceiling:
        gain *= ceiling / peak
    return (audio * gain).astype(np.float32)
