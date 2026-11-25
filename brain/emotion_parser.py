"""
emotion_parser.py — Extracts emotion tags from Hermes responses.

Parses the [emotion] prefix from response text and returns the emotion name
and cleaned text separately.
"""

import re

VALID_EMOTIONS = frozenset([
    "happy", "sad", "surprised", "thinking", "teasing", "concerned",
    "excited", "neutral", "angry", "shy", "sleepy", "love",
    "defeated", "curious", "flustered", "shocked"
])

_EMOTION_PATTERN = re.compile(r"\[(\w+)\]\s*", re.IGNORECASE)


def parse_response(text: str) -> tuple[str, str]:
    """
    Parse emotion tag from Hermes response.

    Returns (emotion_name, clean_text).

    Examples:
        "[excited] Oh wow!" → ("excited", "Oh wow!")
        "No tag here" → ("neutral", "No tag here")
        "[unknown] Hello" → ("neutral", "Hello")
        "[happy] Text [sad] more" → ("happy", "Text more")  # removes ALL tags
    """
    if not text or not text.strip():
        return ("neutral", "")

    # Find first valid emotion tag
    first_emotion = "neutral"
    for match in _EMOTION_PATTERN.finditer(text):
        emotion = match.group(1).lower()
        if emotion in VALID_EMOTIONS:
            first_emotion = emotion
            break

    # Remove ALL emotion tags from text (valid or invalid)
    clean_text = _EMOTION_PATTERN.sub("", text).strip()

    return (first_emotion, clean_text)


def parse_multi_emotions(text: str) -> list[tuple[str, str]]:
    """
    Parse a response string containing multiple emotion tags into a list of
    (emotion, text) segments.

    Example:
        "[excited] Oh wow! [shy] I am shy."
        -> [("excited", "Oh wow!"), ("shy", "I am shy.")]

        "Hello! [happy] Nice to meet you."
        -> [("neutral", "Hello!"), ("happy", "Nice to meet you.")]
    """
    if not text or not text.strip():
        return []

    # Find all emotion tags and their span indices
    matches = list(_EMOTION_PATTERN.finditer(text))

    if not matches:
        return [("neutral", text.strip())]

    segments = []
    last_idx = 0
    current_emotion = "neutral"

    for match in matches:
        start, end = match.span()
        # If there is text before this tag, it belongs to the previous emotion
        if start > last_idx:
            segment_text = text[last_idx:start].strip()
            if segment_text:
                segment_clean = _EMOTION_PATTERN.sub("", segment_text).strip()
                if segment_clean:
                    segments.append((current_emotion, segment_clean))

        # Update current emotion if it is a valid emotion
        tag = match.group(1).lower()
        if tag in VALID_EMOTIONS:
            current_emotion = tag

        last_idx = end

    # Add the remaining text after the last tag
    if last_idx < len(text):
        segment_text = text[last_idx:].strip()
        segment_clean = _EMOTION_PATTERN.sub("", segment_text).strip()
        if segment_clean:
            segments.append((current_emotion, segment_clean))

    # If segments list is empty (e.g. text only had tags like "[happy]"), return at least a neutral empty segment
    if not segments:
        return [("neutral", "")]

    return segments



# Instant, local read of a message so her face reacts before the model answers; first match wins.
_QUICK = (
    ('concerned', re.compile(r'\b(?:sedih|capek|cape|lelah|sakit|pusing|gagal|nangis|stres|stress|takut|'
                             r'sad|tired|sick|exhausted|anxious|scared|failed)\b', re.I)),
    ('happy', re.compile(r'\b(?:wkwk\w*|haha\w*|hehe\w*|lol|makasih|terima kasih|thanks?|thank you|seneng|'
                         r'senang|yay|asik|asyik|berhasil|lulus|passed|finally)\b', re.I)),
    ('surprised', re.compile(r'\b(?:wow|serius|beneran|astaga|hah|omg|seriously|no way)\b', re.I)),
    ('curious', re.compile(r'\?\s*$|^\s*(?:apa|apakah|kenapa|mengapa|gimana|bagaimana|kapan|siapa|di ?mana|'
                           r'why|how|what|when|who|where)\b', re.I)),
)


def quick_reaction(text):
    """The emotion her face shows at once for this message, or None (keep the thinking pose)."""
    return next((emotion for emotion, pattern in _QUICK if pattern.search(text or '')), None)
