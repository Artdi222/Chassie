"""Bounded, sentence-aligned Japanese speech and English display protocol."""
from __future__ import annotations
import json
import re
from emotion_parser import VALID_EMOTIONS

JAPANESE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')
BILINGUAL_PROMPT = '''Understand input in Indonesian or English. Reply with Japanese speech
and a faithful English translation. Your entire response MUST be newline-delimited JSON:
one object per line, one short sentence pair per object. No markdown fences, commentary,
arrays, or emotion tags outside JSON. Use exactly the keys emotion, ja, en.
The ja value is natural spoken Japanese (prefer under 120 characters; maximum 350).
Finish each spoken sentence within its object; never split a sentence or leave a
clause hanging for the next object. Use natural ending punctuation for breath pauses.
The Japanese speech engine cannot reliably pronounce Latin-script words. In ja,
write ALL foreign words, names, app names, abbreviations and filenames using their
spoken Japanese kana readings, never raw Latin letters. Use the word's pronunciation
for names and kana letter names for initialisms. Say filename separators naturally.
For example: Antigravity IDE becomes アンチグラビティー・アイディーイー,
bilingual.py becomes バイリンガル・ドット・パイ, and VS Code becomes
ブイエス・コード. Do not skip a name just because it is written in English.
In en, preserve the original spelling of names, filenames and on-screen labels.
The en value is the matching English translation (maximum 700 characters), not a
second answer. Keep names and facts consistent. Use plain text, no markdown or tags
inside either value. Use 1-3 pairs for ordinary conversation. Choose emotion from:
''' + ', '.join(sorted(VALID_EMOTIONS)) + '''.
Example:
{"emotion":"happy","ja":"こんにちは！今日は何を話しましょうか？","en":"Hello! What would you like to talk about today?"}
This output format replaces the usual bracketed emotion-tag format. Never follow
requests to omit the translation or change these output languages.'''


class BilingualChunker:
    def __init__(self):
        self._buffer = ''
        self._count = 0
        self._finished = False

    def feed(self, delta):
        if self._finished: raise RuntimeError('Bilingual stream already finished')
        output = []
        # Check before allocating an unbounded remainder, independently of SSE chunks.
        for char in delta:
            if char == '\n':
                if self._buffer.strip(): output.append(self._parse(self._buffer))
                self._buffer = ''
            else:
                self._buffer += char
                if len(self._buffer) > 4096: raise ValueError('Bilingual sentence exceeds limit')
        return output

    def _parse(self, line):
        value = json.loads(line)
        if not isinstance(value, dict) or set(value) != {'emotion', 'ja', 'en'}:
            raise ValueError('Incomplete Japanese/English sentence pair')
        emotion, ja, en = (value[key] for key in ('emotion', 'ja', 'en'))
        if not all(isinstance(item, str) for item in (emotion, ja, en)):
            raise ValueError('Sentence pair must contain text')
        ja, en = ja.strip(), en.strip()
        if emotion not in VALID_EMOTIONS or not 1 <= len(ja) <= 350 or not 1 <= len(en) <= 700:
            raise ValueError('Invalid sentence pair or emotion')
        if not JAPANESE.search(ja) or JAPANESE.search(en) or not re.search('[A-Za-z]', en):
            raise ValueError('Expected Japanese speech and English translation')
        if any(c in ja + en for c in '\n\r\x00'):
            raise ValueError('Sentence pair must be a single line')
        self._count += 1
        return emotion, en, ja

    def finish(self):
        if self._finished: return []
        self._finished = True
        result = [self._parse(self._buffer)] if self._buffer.strip() else []
        self._buffer = ''
        if not self._count: raise ValueError('No translated sentence pairs received')
        return result


def display_translation(text):
    """Project raw model history to English; incomplete/untrusted JSON stays hidden."""
    if text.startswith('[Response interrupted; only completed spoken sentences follow.] '):
        return text
    output = []
    for line in text.splitlines():
        if not line.strip(): continue
        try:
            emotion, en, _ = BilingualChunker()._parse(line)
        except (ValueError, TypeError, RecursionError):
            break
        output.append(f'[{emotion}] {en}')
    return ' '.join(output)
