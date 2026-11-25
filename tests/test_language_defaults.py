import datetime as dt

from brain.bilingual import bilingual_prompt
from memory import reflection


def test_prompt_follows_the_subtitle_language():
    english, indonesian = bilingual_prompt('en'), bilingual_prompt('id')
    assert '"you"' in english and 'kamu' not in english and 'English reminder' in english
    assert '"kamu"' in indonesian and 'Indonesian note title' in indonesian
    assert 'Artdi' not in english + indonesian


def test_diary_is_written_in_the_subtitle_language():
    day = dt.date(2026, 11, 25)
    assert "# Chassie's diary 2026-11-25" in reflection.note_markdown(day, 'A quiet day.', ['Ask about it'])
    assert '## Yang perlu ditanyakan lagi' in reflection.note_markdown(day, 'Hari tenang.', ['Tanya'], 'id')
    assert 'in Indonesian' in reflection.system_prompt('id') and 'in English' in reflection.SYSTEM
