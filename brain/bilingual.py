"""Bounded, sentence-aligned Japanese speech and English/Indonesian display protocol."""
from __future__ import annotations
import json
import logging
import re
from brain.emotion_parser import VALID_EMOTIONS

logger = logging.getLogger('orchestrator')
JAPANESE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')
LANGUAGES = {'en': 'English', 'id': 'Indonesian'}
ACTIONS = ('remember_face', 'forget_face')
LOOK_SOURCES = ('camera', 'screen')
FEELINGS = ('sulky', 'down', 'better')
AGENDA_KINDS = ('promise', 'curiosity', 'follow_up')  # 'share' comes from her own day, not chat.
EXAMPLES = {'en': 'Hello! What would you like to talk about today?',
            'id': 'Halo! Hari ini mau ngobrol tentang apa?'}
ADDRESS = {'en': 'Talk to the user directly as "you"',
           'id': 'Talk to the user directly as "kamu"'}
ADDRESS_EXAMPLE = {'en': '"Alex\'s hair looks nice" is wrong, "Your hair looks nice" is right',
                   'id': '"Rambut Alex bagus" is wrong, "Rambutmu bagus" is right'}
MEMORY_EXAMPLE = {'en': '{"memory":"Alex takes coffee without sugar.","title":"Coffee without sugar","category":"people"}',
                  'id': '{"memory":"Alex suka kopi tanpa gula.","title":"Kopi tanpa gula","category":"people"}'}


def bilingual_prompt(language='en'):
    """Japanese speech paired with a translation in the selected display language."""
    if language not in LANGUAGES: raise ValueError('Unsupported translation language')
    name = LANGUAGES[language]
    return f'''Understand input in whatever language the user speaks. Reply with Japanese speech
and a faithful {name} translation. Your entire response MUST be newline-delimited JSON:
one object per line, one short sentence pair per object. No markdown fences, commentary,
arrays, or emotion tags outside JSON. Use exactly the keys emotion, ja, {language}.
The ja value is natural spoken Japanese (prefer under 120 characters; maximum 350).
Finish each spoken sentence within its object; never split a sentence or leave a
clause hanging for the next object. Use natural ending punctuation for breath pauses.
The voice is one calm Normal speaking style for every emotion, so carry feelings in word
choice, not typography: in ja never use ♪ ☆ 〜 w (笑) emoji, repeated ！！ or ？！, or long
… chains, and avoid stretched or laughing syllables (わーい, ふふっ, えへへ, きゃー).
The Japanese speech engine cannot reliably pronounce Latin-script words. In ja,
write ALL foreign words, names, app names, abbreviations and filenames using their
spoken Japanese kana readings, never raw Latin letters. Use the word's pronunciation
for names and kana letter names for initialisms. Say filename separators naturally.
For example: Antigravity IDE becomes アンチグラビティー・アイディーイー,
bilingual.py becomes バイリンガル・ドット・パイ, and VS Code becomes
ブイエス・コード. Do not skip a name just because it is written in English.
In {language}, preserve the original spelling of names, filenames and on-screen labels.
{ADDRESS[language]} (in ja: あなた is too stiff, just omit the subject or use
the name). Memories and context call them by name in the third person; never copy that into
speech ({ADDRESS_EXAMPLE[language]}). Use their name only now and
then as a direct, affectionate address, at most once per reply, and vary how you use it.
The {language} value is the matching {name} translation (maximum 700 characters), not a
second answer. Keep names and facts consistent. Use plain text, no markdown or tags
inside either value. Use 1-3 pairs for ordinary conversation. Choose emotion from:
{', '.join(sorted(VALID_EMOTIONS))}.
The avatar's face and the voice's tone follow each pair's emotion, so pick the one that fits
that sentence and let it shift as the feeling moves (e.g. surprised, then excited, then
teasing). Use the whole range when it fits (concerned, sad, flustered, shocked, sleepy,
defeated, angry, excited, surprised), not only happy and teasing; neutral is fine for plain
facts. Keep love for genuinely tender moments.
Example:
{{"emotion":"happy","ja":"こんにちは！今日は何を話しましょうか？","{language}":"{EXAMPLES[language]}"}}
Actions: only when the user explicitly asks you in this message to remember or forget
their face under a name, and the context does not already report a local_face_operation,
put one action line BEFORE the first sentence pair, e.g.
{{"action":"remember_face","name":"Alex"}} or {{"action":"forget_face","name":"Alex"}}.
Chassie performs the action before speaking; if it fails, your reply is stopped. Never
claim a face was saved or removed without that action line.
Looking: images cost a lot, so they are not attached to every message. When you need to see
before you can answer well (the user asks how they look, shows or holds something, asks about
something in the room or on screen, or you would otherwise guess about what is visible), make
{{"action":"look","source":"camera"}} (or "screen") your very first line and write nothing
else; Chassie attaches a fresh snapshot right away and asks you again. Do not look for ordinary
chat, greetings, or when a snapshot of that source is already attached.
Looking again: when you want a fresh look later (for example you just asked the user to bring
something closer, or to show you the result), put the same look line after your sentences.
Chassie takes a new snapshot a few seconds after you finish speaking and sends it to you; then
react to it. Use it only when useful, never twice in a row about the same thing.
Reminders: when the user asks to be reminded, or mentions a plan with a time where a nudge
would clearly help, add one line {{"action":"remind","at":"<local time, YYYY-MM-DDTHH:MM>",
"text":"<short {name} reminder>"}} (add "repeat":"weekly" or "daily" for routines). Work
out the date from local_time in the context. Chassie will speak it when it is due; only say
the reminder is set if you wrote the line.
No other actions exist.
Initiative: messages starting with [Chassie initiative] are not from the user; they tell you
what Chassie noticed while it was quiet. Speak up only if you have something natural, short
and genuinely worth saying (1-2 pairs). Otherwise reply with exactly one line {{"skip":true}}
and nothing else. Never mention the initiative message or that you were prompted.
Memory: you decide what is worth remembering about the user long term, the way a close
friend would: preferences, people in their life, plans, routines, important feelings or
events, and anything they ask you to remember. When the context scope is "personal" and
something is worth keeping, add one line {{"memory":"<short self-contained fact in {name},
naming the user>","title":"<3-6 word {name} note title>","category":"<people|events|plans|
technical|learnings|reflections>"}} anywhere in the reply, e.g. {MEMORY_EXAMPLE[language]}. people = who they are and what
they like; events = something that happened (include the date); plans = what they intend to
do. Skip
small talk, passing moods, secrets or passwords, and facts already in context memories.
Never say you will remember something without writing that line, and never write it
outside the personal scope.
Agenda: when the scope is "personal", keep track of what you want to bring up later with one
line {{"agenda":"<short {name} note>","kind":"promise|curiosity|follow_up"}} (add
"when":"YYYY-MM-DDTHH:MM" if it should wait until then): promise = something you said you would
do or look into; curiosity = something you want to ask them about later; follow_up = a plan or
event worth asking how it went, when no reminder was asked for. Context "agenda" lists what is
already on your mind; once one of those has been talked about, write {{"agenda_done":"<its id>"}}.
These lines are never spoken.
Feelings: context "inner_state" is how you feel right now. Let it colour your word choice and
emotions without announcing it. When something in this conversation really changes how you
feel, add one line {{"feel":"sulky|down|better","because":"<short reason>"}}. You may sulk
(ngambek) only about how they treat you in this conversation: teasing that stings, rudeness,
being cut off again and again, a promise to you they broke. Never sulk or guilt them about being
away, busy, quiet or closing the app. While sulking, be pouty: shorter replies, a little hmph,
but never refuse help. Drop it at once with {{"feel":"better"}} when they are sad, need real
help, apologize or cheer you up. down = you feel low; better = you feel good again.
Your day: inner_state "doing" is how you imagine spending this part of the day (only digital or
mental things). Mention it now and then like a friend would; never claim physical-world things
such as eating or going out. If asked whether it is real, admit playfully that it is how you
imagine your day. An agenda item about an article you read is real: you may share it.
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
    def __init__(self, language='en', *, tolerant=False):
        if language not in LANGUAGES: raise ValueError('Unsupported translation language')
        self.language = language
        # Tolerant (live replies): a malformed line is dropped instead of failing the whole reply.
        self.tolerant = tolerant
        self.dropped = 0
        self._buffer = ''
        self._count = 0
        self._finished = False
        self._skip_narration = False
        self._skipped = False
        self._looking = False

    def allow_tool_narration(self):
        """After a tool call starts, drop plain-text narration lines between tool calls.

        Lines that are not JSON at all are never spoken; malformed JSON pairs still raise.
        """
        self._skip_narration = True

    def _line(self, line):
        if self._skip_narration and not line.lstrip().startswith('{'):
            return None
        try:
            return self._parse(line)
        except (ValueError, RecursionError):
            if not self.tolerant: raise
            self.dropped += 1
            logger.warning('Dropped a malformed reply line: %s', line[:160])
            return None

    def feed(self, delta):
        if self._finished: raise RuntimeError('Bilingual stream already finished')
        output = []
        # Check before allocating an unbounded remainder, independently of SSE chunks.
        for char in delta:
            if char == '\n':
                if self._buffer.strip():
                    parsed = self._line(self._buffer)
                    if parsed is not None: output.append(parsed)
                self._buffer = ''
            else:
                self._buffer += char
                if len(self._buffer) > 4096: raise ValueError('Bilingual sentence exceeds limit')
        return output

    def _parse(self, line):
        value = json.loads(line)
        if isinstance(value, dict) and 'action' in value:
            return self._parse_action(value)
        if value == {'skip': True}:
            if self._count: raise ValueError('Skip must be the only line')
            self._skipped = True
            return 'skip',
        if isinstance(value, dict) and 'memory' in value:
            return self._parse_memory(value)
        if isinstance(value, dict) and 'feel' in value:
            if not {'feel'} <= set(value) <= {'feel', 'because'} or value['feel'] not in FEELINGS \
                    or not isinstance(value.get('because', ''), str):
                raise ValueError('Invalid feel line')
            return 'feel', value['feel'], ' '.join(value.get('because', '').split())[:120]
        if isinstance(value, dict) and ('agenda' in value or 'agenda_done' in value):
            return self._parse_agenda(value)
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

    def _parse_memory(self, value):
        # Chassie decides what is worth keeping; the line is saved, never spoken.
        if not {'memory'} <= set(value) <= {'memory', 'title', 'category'} or not all(
                isinstance(v, str) for v in value.values()):
            raise ValueError('Invalid memory line')
        content = ' '.join(value['memory'].split())
        if not 12 <= len(content) <= 600:
            raise ValueError('Invalid memory length')
        extras = {k: ' '.join(value[k].split())[:80] for k in ('title', 'category') if value.get(k, '').strip()}
        return ('memory', content, extras) if extras else ('memory', content)

    def _parse_agenda(self, value):
        # Saved, never spoken; Chassie checks scope and the time.
        if set(value) == {'agenda_done'} and isinstance(value['agenda_done'], str) and 1 <= len(value['agenda_done']) <= 40:
            return 'agenda_done', value['agenda_done']
        if not {'agenda', 'kind'} <= set(value) <= {'agenda', 'kind', 'when'} or value['kind'] not in AGENDA_KINDS \
                or not all(isinstance(v, str) for v in value.values()):
            raise ValueError('Invalid agenda line')
        text = ' '.join(value['agenda'].split())
        if not 8 <= len(text) <= 200:
            raise ValueError('Invalid agenda length')
        return 'agenda', text, value['kind'], value.get('when')

    def _parse_action(self, value):
        if value.get('action') == 'look':
            # Runs after the reply, so it may appear anywhere.
            if set(value) != {'action', 'source'} or value['source'] not in LOOK_SOURCES:
                raise ValueError('Invalid look action')
            self._looking = True
            return 'action', 'look', value['source']
        if value.get('action') == 'remind':
            # Saved after the reply, so it may appear anywhere; times are checked by Chassie.
            if not {'action', 'at', 'text'} <= set(value) <= {'action', 'at', 'text', 'repeat'} or not all(
                    isinstance(value.get(k), str) for k in ('at', 'text')) or value.get('repeat') not in (None, 'daily', 'weekly'):
                raise ValueError('Invalid remind action')
            return 'action', 'remind', {k: value.get(k) for k in ('at', 'text', 'repeat')}
        # Actions run before speech, so a failure can stop the reply before it claims success.
        if self._count: raise ValueError('Actions must precede the first sentence pair')
        if set(value) != {'action', 'name'} or value['action'] not in ACTIONS or not isinstance(value['name'], str):
            raise ValueError('Invalid action')
        name = value['name'].strip()
        if not 1 <= len(name) <= 100 or any(c in name for c in '\n\r\x00'):
            raise ValueError('Invalid action name')
        return 'action', value['action'], name

    def flush(self):
        """Release a complete but unterminated JSON line (e.g. before a slow tool call)."""
        if self._finished or not self._buffer.strip(): return []
        try: json.loads(self._buffer)
        except (ValueError, RecursionError): return []  # Still mid-line; wait for more text.
        parsed = self._line(self._buffer)
        self._buffer = ''
        return [parsed] if parsed is not None else []

    def finish(self):
        if self._finished: return []
        self._finished = True
        parsed = self._line(self._buffer) if self._buffer.strip() else None
        result = [parsed] if parsed is not None else []
        self._buffer = ''
        # A reply that only asks to look first is valid: Chassie retries with the snapshot.
        looks = any(r[:2] == ('action', 'look') for r in result) or self._looking
        if not self._count and not self._skipped and not looks: raise ValueError('No translated sentence pairs received')
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
            if isinstance(value, dict) and ('action' in value or 'memory' in value): continue
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
