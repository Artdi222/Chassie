import random

import pytest

from speech.speech_chunker import SpeechChunker


def parse(parts, max_chars=350):
    parser = SpeechChunker(max_chars=max_chars)
    chunks = []
    for part in parts:
        chunks.extend(parser.feed(part))
    chunks.extend(parser.finish())
    return chunks


def test_complete_sentences_stream_before_finish_with_lookahead():
    parser = SpeechChunker()
    assert parser.feed('[hap') == []
    assert parser.feed('py] Hello.') == []
    assert parser.feed(' Next') == [('happy', 'Hello.')]
    assert parser.feed(' sentence! ') == [('happy', 'Next sentence!')]
    assert parser.finish() == []


def test_tag_flushes_unfinished_phrase_and_changes_only_following_text():
    assert parse(['Before [happy]hello there[sad]sorry.[neutral]Done']) == [
        ('neutral', 'Before'), ('happy', 'hello there'), ('sad', 'sorry.'), ('neutral', 'Done')]


def test_unknown_brackets_are_preserved_and_known_tags_case_insensitive():
    assert parse(['[HAPPY] Read [unknown], [a,b], and [[sad]nested.']) == [
        ('happy', 'Read [unknown], [a,b], and ['), ('sad', 'nested.')]


def test_abbreviations_decimals_initials_and_quotes():
    text = '[thinking] Dr. A. Smith met Mr. Jones at 3.14 p.m. They said "Hi!" Is that right? Yes.'
    assert parse([text]) == [
        ('thinking', 'Dr. A. Smith met Mr. Jones at 3.14 p.m. They said "Hi!"'),
        ('thinking', 'Is that right?'), ('thinking', 'Yes.')]
    assert parse(['Use e.g. 2.5 or i.e. 3.0. Continue.']) == [
        ('neutral', 'Use e.g. 2.5 or i.e. 3.0.'), ('neutral', 'Continue.')]


def test_ellipsis_and_punctuation_runs_remain_whole():
    assert parse(['Wait... What?! "Really?" Yes.']) == [
        ('neutral', 'Wait...'), ('neutral', 'What?!'), ('neutral', '"Really?"'), ('neutral', 'Yes.')]


def test_invariant_for_every_two_way_split_character_chunks_and_random_splits():
    text = '[happy]Dr. A. Smith paid 3.14. [curious]Really?! [unknown] Yes, e.g. that one[shy]unfinished [hap'
    expected = parse([text])
    assert parse(list(text)) == expected
    for split in range(len(text) + 1):
        assert parse([text[:split], text[split:]]) == expected
    rng = random.Random(17)
    for _ in range(30):
        cuts = sorted(rng.sample(range(len(text) + 1), 12))
        parts = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
        assert parse(parts) == expected


def test_unpunctuated_text_is_bounded_at_word_boundaries():
    text = '[happy]' + 'alpha beta gamma delta ' * 20 + '[sad]end'
    chunks = parse([text], max_chars=30)
    assert chunks == parse(list(text), max_chars=30)
    assert all(0 < len(chunk) <= 30 for _, chunk in chunks)
    assert ' '.join(chunk for emotion, chunk in chunks if emotion == 'happy').split() == ('alpha beta gamma delta ' * 20).split()
    assert chunks[-1] == ('sad', 'end')


def test_long_single_word_is_hard_bounded_without_loss():
    chunks = parse(['a' * 81], max_chars=20)
    assert ''.join(text for _, text in chunks) == 'a' * 81
    assert all(len(text) <= 20 for _, text in chunks)


@pytest.mark.parametrize('tail', ['[', '[hap', '[HAPP', '[neutral', '[shocked'])
def test_finish_discards_dangling_known_tag_prefix(tail):
    assert parse(['Hello ' + tail]) == [('neutral', 'Hello')]


def test_finish_preserves_unrecognized_brackets_and_is_idempotent():
    parser = SpeechChunker()
    assert parser.feed('[haphazard') == []
    assert parser.finish() == [('neutral', '[haphazard')]
    assert parser.finish() == []
    with pytest.raises(RuntimeError): parser.feed('more')


def test_no_empty_chunks_for_only_tags_spaces_or_empty_input():
    assert parse(['', ' ', '[happy]', '[sad]', '\n', '']) == []


@pytest.mark.parametrize('limit', [0, -1, 3.5, True])
def test_invalid_max_chars_rejected(limit):
    with pytest.raises(ValueError): SpeechChunker(limit)


def test_invalid_delta_does_not_consume_pending_text():
    parser = SpeechChunker()
    parser.feed('[happy]Pending')
    with pytest.raises(TypeError): parser.feed(None)
    assert parser.finish() == [('happy', 'Pending')]


def test_very_small_limit_never_emits_oversized_or_empty_chunks():
    for limit in (1, 2, 3, 8):
        text = '[happy] A. Smith... yes?! [sad]abcdefghijklmnop'
        result = parse([text], max_chars=limit)
        assert result == parse(list(text), max_chars=limit)
        assert all(0 < len(chunk) <= limit for _, chunk in result)
