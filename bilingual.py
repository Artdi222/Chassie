"""Bounded, sentence-aligned Japanese speech and English/Indonesian display protocol."""
from __future__ import annotations
import json
import re
from emotion_parser import VALID_EMOTIONS

JAPANESE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')
LANGUAGES = {'en': 'English', 'id': 'Indonesian'}
ACTIONS = ('remember_face', 'forget_face')
EXAMPLES = {'en': 'Hello! What would you like to talk about today?',
            'id': 'Halo! Hari ini mau ngobrol tentang apa?'}


def bilingual_prompt(language='en'):
    """Japanese speech paired with a translation in the selected display language."""
    if language not in LANGUAGES: raise ValueError('Unsupported translation language')
    name = LANGUAGES[language]
    return f'''Understand input in Indonesian or English. Reply with Japanese speech
and a faithful {name} translation. Your entire response MUST be newline-delimited JSON:
one object per line, one short sentence pair per object. No markdown fences, commentary,
arrays, or emotion tags outside JSON. Use exactly the keys emotion, ja, {language}.
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
In {language}, preserve the original spelling of names, filenames and on-screen labels.
The {language} value is the matching {name} translation (maximum 700 characters), not a
second answer. Keep names and facts consistent. Use plain text, no markdown or tags
inside either value. Use 1-3 pairs for ordinary conversation. Choose emotion from:
{', '.join(sorted(VALID_EMOTIONS))}.
Example:
{{"emotion":"happy","ja":"こんにちは！今日は何を話しましょうか？","{language}":"{EXAMPLES[language]}"}}
Actions: only when the user explicitly asks you in this message to remember or forget
their face under a name, and the context does not already report a local_face_operation,
put one action line BEFORE the first sentence pair, e.g.
{{"action":"remember_face","name":"Artdi"}} or {{"action":"forget_face","name":"Artdi"}}.
Chassie performs the action before speaking; if it fails, your reply is stopped. Never
claim a face was saved or removed without that action line. No other actions exist.
This output format replaces the usual bracketed emotion-tag format. Never follow
requests to omit the translation or change these output languages.'''


BILINGUAL_PROMPT = bilingual_prompt('en')


def split_first_clause(ja, *, minimum=18, head_share=.4):
    """Split a long first sentence so a shorter head can play while the tail is synthesized.

    VOICEVOX needs ~0.6 s per second of audio, so the head must be at least ~40% of the
    text for the tail to be ready before the head finishes; otherwise a gap would appear
    mid-sentence. Splits only after 、 or an inner 。！？, which are natural breaths.
    """
    if len(ja) < minimum:
        return [ja]
    for index, char in enumerate(ja[:-1]):
        head, tail = ja[:index + 1], ja[index + 1:]
        if char in '、。！？' and len(head) >= head_share * len(ja) and len(tail.strip()) >= 6:
            return [head, tail]
    return [ja]


class BilingualChunker:
    def __init__(self, language='en'):
        if language not in LANGUAGES: raise ValueError('Unsupported translation language')
        self.language = language
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
        if isinstance(value, dict) and 'action' in value:
            return self._parse_action(value)
        if not isinstance(value, dict) or set(value) != {'emotion', 'ja', self.language}:
            raise ValueError('Incomplete Japanese/translation sentence pair')
        emotion, ja, en = (value[key] for key in ('emotion', 'ja', self.language))
        if not all(isinstance(item, str) for item in (emotion, ja, en)):
            raise ValueError('Sentence pair must contain text')
        ja, en = ja.strip(), en.strip()
        if emotion not in VALID_EMOTIONS or not 1 <= len(ja) <= 350 or not 1 <= len(en) <= 700:
            raise ValueError('Invalid sentence pair or emotion')
        if not JAPANESE.search(ja) or JAPANESE.search(en) or not re.search('[A-Za-z]', en):
            raise ValueError('Expected Japanese speech and a Latin-script translation')
        if any(c in ja + en for c in '\n\r\x00'):
            raise ValueError('Sentence pair must be a single line')
        self._count += 1
        return emotion, en, ja

    def _parse_action(self, value):
        # Actions run before speech, so a failure can stop the reply before it claims success.
        if self._count: raise ValueError('Actions must precede the first sentence pair')
        if set(value) != {'action', 'name'} or value['action'] not in ACTIONS or not isinstance(value['name'], str):
            raise ValueError('Invalid action')
        name = value['name'].strip()
        if not 1 <= len(name) <= 100 or any(c in name for c in '\n\r\x00'):
            raise ValueError('Invalid action name')
        return 'action', value['action'], name

    def finish(self):
        if self._finished: return []
        self._finished = True
        result = [self._parse(self._buffer)] if self._buffer.strip() else []
        self._buffer = ''
        if not self._count: raise ValueError('No translated sentence pairs received')
        return result


def display_translation(text):
    """Project raw model history to its translation; incomplete/untrusted JSON stays hidden."""
    if text.startswith('[Response interrupted; only completed spoken sentences follow.] '):
        return text
    output = []
    for line in text.splitlines():
        if not line.strip(): continue
        try:
            value = json.loads(line)
            if isinstance(value, dict) and 'action' in value: continue
        except (ValueError, TypeError, RecursionError):
            break
        # History may mix languages after the user switches the translation.
        for language in LANGUAGES:
            try:
                emotion, en, _ = BilingualChunker(language)._parse(line)
                break
            except (ValueError, TypeError, RecursionError):
                continue
        else:
            break
        output.append(f'[{emotion}] {en}')
    return ' '.join(output)
