"""Incremental speech chunks with emotion ownership independent of SSE boundaries."""
from __future__ import annotations

import re

from emotion_parser import VALID_EMOTIONS

_TAGS = {f'[{emotion}]': emotion for emotion in VALID_EMOTIONS}
_TAG_PREFIXES = frozenset(tag[:length] for tag in _TAGS for length in range(1, len(tag)))
_SENTENCE_END = re.compile(r'''([.!?]+)["'”’)\]]*(?=\s)''')
_ABBREVIATION = re.compile(
    r'(?:\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|St|vs|etc|approx|dept|Fig)\.'
    r'|\b(?:[A-Za-z]\.){2,}|\b[A-Za-z]\.)$', re.IGNORECASE,
)


class SpeechChunker:
    """Turn text deltas into ordered ``(emotion, text)`` speech segments.

    Known emotion tags flush the prior phrase. Unknown bracket text stays literal.
    A sentence streams once its final punctuation (and optional closing quote) has
    whitespace lookahead. Decimal points and common abbreviations/initials do not
    end sentences. Abbreviations at a true sentence end conservatively wait for the
    next boundary or ``finish`` rather than guessing from semantic context.

    Chunks trim boundary whitespace, retain internal text, and never exceed
    ``max_chars``. A word longer than the limit is split only as a last resort.
    Feed partitioning cannot change the resulting chunks: parsing advances one
    Unicode character at a time, including tag-prefix buffering and length cuts.
    """
    def __init__(self, max_chars: int = 350):
        if type(max_chars) is not int or max_chars < 1:
            raise ValueError('max_chars must be a positive integer')
        self.max_chars = max_chars
        self._emotion = 'neutral'
        self._text = ''
        self._tag = ''
        self._finished = False

    def feed(self, delta: str) -> list[tuple[str, str]]:
        if self._finished:
            raise RuntimeError('Cannot feed a finished SpeechChunker')
        if not isinstance(delta, str):
            raise TypeError('Speech delta must be text')
        output: list[tuple[str, str]] = []
        for character in delta:
            self._consume(character, output)
        return output

    def finish(self) -> list[tuple[str, str]]:
        if self._finished:
            return []
        self._finished = True
        # This is necessarily a prefix of a known tag; all disproven prefixes
        # have already been released literally. Never send a torn emotion tag
        # such as "[hap" to speech when the stream is interrupted or ends early.
        self._tag = ''
        output: list[tuple[str, str]] = []
        self._flush(output)
        return output

    def _consume(self, character: str, output: list[tuple[str, str]]):
        if self._tag:
            self._tag += character
            candidate = self._tag.lower()
            if candidate in _TAGS:
                self._flush(output)
                self._emotion = _TAGS[candidate]
                self._tag = ''
            elif candidate not in _TAG_PREFIXES:
                # Preserve the failed prefix, while allowing a nested '[' to
                # begin a real tag (e.g. '[[happy]'). Prefix length is bounded.
                rejected, self._tag = self._tag, ''
                self._append_text(rejected[0], output)
                for char in rejected[1:]:
                    self._consume(char, output)
        elif character == '[':
            self._tag = '['
        else:
            self._append_text(character, output)

    def _append_text(self, character: str, output: list[tuple[str, str]]):
        self._text += character
        while self._text:
            boundary = self._sentence_boundary()
            if boundary is not None:
                text, self._text = self._text[:boundary], self._text[boundary:]
                self._emit(text, output)
            elif len(self._text) > self.max_chars:
                whitespace = [index for index, char in enumerate(self._text[:self.max_chars + 1])
                              if char.isspace()]
                cut = whitespace[-1] if whitespace and whitespace[-1] > 0 else self.max_chars
                text, self._text = self._text[:cut], self._text[cut:].lstrip()
                self._emit(text, output)
            else:
                break

    def _sentence_boundary(self) -> int | None:
        for match in _SENTENCE_END.finditer(self._text):
            if match.group(1) == '.' and _ABBREVIATION.search(self._text[:match.end(1)]):
                continue
            return match.end()
        return None

    def _emit(self, text: str, output: list[tuple[str, str]]):
        text = text.strip()
        if text:
            output.append((self._emotion, text))

    def _flush(self, output: list[tuple[str, str]]):
        self._emit(self._text, output)
        self._text = ''
