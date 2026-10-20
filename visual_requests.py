"""Conservative, per-message visual requests without an extra model call."""
import re

_SOURCES = {
    'screen': re.compile(r'\b(?:layar(?:ku|mu|nya)?|screen(?:shot)?s?|desktop|monitor)\b'),
    'camera': re.compile(r'\b(?:kamera(?:ku|mu|nya)?|camera|webcam)\b'),
}
_ACTION = re.compile(
    r'\b(?:lihat(?:in)?|liat(?:in)?|cek|periksa|baca(?:kan)?|jelaskan|deskripsikan|'
    r'look|see|check|inspect|read|describe|analy[sz]e|explain)\b')
_QUESTION = re.compile(
    r'\b(?:apa (?:yang |aja |saja )?(?:ada|terlihat|tampil)|'
    r'what(?:\s+is|\s+are|\x27s)\s+(?:visible|shown|displayed|on|in)|'
    r'what\s+(?:can|do) you see)\b')
_PERSON = re.compile(
    r'\b(?:(?:lihat|liat)\s+(?:aku|saya|wajahku|mukaku)|see\s+me)\b')
_NEGATIVE = re.compile(r"\b(?:jangan|jgn|tidak|nggak|gak|ga|tak|bukan|not|never|without|don't|do not)\b")
_META = re.compile(r'\b(?:translate|terjemahkan|terjemahin|arti|artinya|meaning|how to|cara)\b')
_REQUEST_PREFIX = re.compile(
    r'(?:(?:chassie|hey|hi|halo|tolong|coba|bantu|please|kamu|bisa|boleh|dapat|'
    r'can|could|would|will|you|mind)\b[\s,:]*|'
    r'(?:i (?:want|need) you to|aku minta(?: kamu)?(?: untuk)?)\s+)*')


def requested_visual_sources(text):
    """Recognize direct Indonesian/English requests, never carry consent forward.

    Mentions alone, quoted instructions and negated clauses do not attach images.
    Unclear requests stay text-only; users can name the source and ask to see it.
    """
    text = text.casefold().replace('’', "'")
    # Exclude quoted examples and code before evaluating user instructions.
    text = re.sub(r'```[\s\S]*?```|`[^`]*`|"[^"]*"|“[^”]*”|(?<!\w)\x27[^\x27]*\x27', '', text)
    sources = set()
    for clause in re.split(r'[.!?;\n]|\b(?:but|tapi|tetapi)\b', text):
        if _NEGATIVE.search(clause) or _META.search(clause):
            continue
        clause = clause.strip(' ,:')
        action = _ACTION.search(clause)
        direct = action is not None and _REQUEST_PREFIX.fullmatch(clause[:action.start()]) is not None
        question = _QUESTION.match(clause) is not None
        if direct or question:
            sources.update(source for source, pattern in _SOURCES.items() if pattern.search(clause))
        if direct and _PERSON.search(clause):
            sources.add('camera')
    return sources
