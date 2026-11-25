import json
import os

import pytest

import desktop_grant
from bilingual import BilingualChunker
from hermes_bridge import ToolProgress
from speech.speech_chunker import SpeechChunker
from tests.test_hermes_stream import STOP, bridge, delta, server


def tool_event(status, tool='terminal', label='agent-reach reddit search'):
    body = json.dumps({'tool': tool, 'label': label, 'toolCallId': 'c1', 'status': status})
    return f'event: hermes.tool.progress\ndata: {body}\n\n'.encode()


@pytest.mark.asyncio
async def test_tool_progress_is_yielded_between_text_and_kept_out_of_history():
    chunks = [delta('[thinking] Let me check.'), tool_event('running'), tool_event('completed'),
              delta(' [happy] Found it.'), STOP]
    async with server(chunks) as (url, _):
        h = bridge(url)
        await h.connect()
        try:
            items = [item async for item in h.stream_message('look it up')]
        finally:
            await h.close()
    events = [item for item in items if isinstance(item, ToolProgress)]
    assert [e['status'] for e in events] == ['running', 'completed']
    assert events[0]['label'] == 'agent-reach reddit search'
    text = ''.join(item for item in items if not isinstance(item, ToolProgress))
    assert text == '[thinking] Let me check. [happy] Found it.'
    assert h.get_history()[-1]['content'] == text


@pytest.mark.asyncio
async def test_tool_guidance_is_sent_to_hermes():
    async with server([delta('[happy] Hi.'), STOP]) as (url, requests):
        h = bridge(url)
        await h.connect()
        try:
            [item async for item in h.stream_message('hi')]
        finally:
            await h.close()
    system = ' '.join(m['content'] for m in requests[0]['messages'] if m['role'] == 'system')
    assert 'agent-reach' in system and 'OWNER_REQUIRED' in system


def test_speech_chunker_flush_releases_unterminated_sentence_and_keeps_streaming():
    chunker = SpeechChunker()
    assert chunker.feed('[thinking] Let me check.') == []  # waits for whitespace lookahead
    assert chunker.flush() == [('thinking', 'Let me check.')]
    assert chunker.feed(' [happy] Done. ') == [('happy', 'Done.')]
    assert chunker.finish() == []


def test_bilingual_flush_releases_only_complete_lines():
    chunker = BilingualChunker('en')
    line = json.dumps({'emotion': 'thinking', 'ja': 'ちょっと調べるね。', 'en': 'Let me check.'}, ensure_ascii=False)
    chunker.feed(line[:10])
    assert chunker.flush() == []
    chunker.feed(line[10:])
    assert chunker.flush() == [('thinking', 'Let me check.', 'ちょっと調べるね。')]


def test_desktop_grant_round_trip(tmp_path, monkeypatch):
    path = tmp_path / 'chassie' / 'desktop-grant'
    monkeypatch.setattr(desktop_grant, 'grant_path', lambda: path)
    desktop_grant.grant(60)
    assert int(path.read_text()) > 0 and oct(path.stat().st_mode & 0o777) == '0o600'
    desktop_grant.revoke()
    desktop_grant.revoke()
    assert not path.exists()


def test_bilingual_skips_plain_narration_only_after_a_tool_started():
    pair = json.dumps({'emotion': 'happy', 'ja': '見つけたよ。', 'en': 'Found it.'}, ensure_ascii=False)
    strict = BilingualChunker('en')
    with pytest.raises(ValueError):
        strict.feed('list-windows returned nothing\n')
    chunker = BilingualChunker('en')
    chunker.allow_tool_narration()
    assert chunker.feed('list-windows returned nothing\n' + pair + '\n') == [('happy', 'Found it.', '見つけたよ。')]
    with pytest.raises(ValueError):  # malformed JSON pairs are still rejected
        chunker.feed('{"en":"Hello."}\n')


def test_model_memory_lines_are_parsed_hidden_and_validated():
    from bilingual import display_translation
    pair = json.dumps({'emotion': 'happy', 'ja': '覚えたよ。', 'en': 'Got it.'}, ensure_ascii=False)
    memory = json.dumps({'memory': 'Artdi prefers coffee without sugar'})
    chunker = BilingualChunker('en')
    assert chunker.feed(memory + '\n' + pair + '\n') == [('memory', 'Artdi prefers coffee without sugar'),
                                                          ('happy', 'Got it.', '覚えたよ。')]
    assert 'coffee' not in display_translation(memory + '\n' + pair)
    with pytest.raises(ValueError):
        BilingualChunker('en').feed('{"memory":"short"}\n')



def test_memory_line_may_carry_a_title_and_category():
    from bilingual import BilingualChunker
    line = '{"memory":"Artdi suka kopi tanpa gula.","title":"Kopi tanpa gula","category":"people"}\n'
    assert BilingualChunker('en').feed(line) == [
        ('memory', 'Artdi suka kopi tanpa gula.', {'title': 'Kopi tanpa gula', 'category': 'people'})]
