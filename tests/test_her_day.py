import datetime as dt
import json
from unittest.mock import AsyncMock

import pytest

from brain.day import HerDay, parse_day, parse_read
from test_orchestrator import app  # noqa: F401  (fixture)
from test_sessions import make_owner

SLOTS = {'morning': 'reading about lo-fi music producers', 'afternoon': 'watching along on your screen',
         'evening': 'thinking about that guitar song you mentioned', 'night': 'half asleep, listening to rain sounds'}
DAY = dt.datetime(2026, 11, 25, 13, 0)


def test_day_replies_are_validated():
    assert parse_day('Here you go:\n' + json.dumps(SLOTS)) == SLOTS
    for bad in ({**SLOTS, 'night': ''}, {k: v for k, v in SLOTS.items() if k != 'evening'},
                {**SLOTS, 'morning': 'x' * 200}):
        with pytest.raises(ValueError):
            parse_day(json.dumps(bad))


def test_read_replies_are_validated():
    good = {'title': 'Why lo-fi helps focus', 'url': 'https://example.org/lofi', 'gist': 'Steady beats lower distraction.'}
    assert parse_read(json.dumps(good)) == good
    assert parse_read('{"none": true}') is None
    for bad in ({**good, 'url': 'javascript:alert(1)'}, {**good, 'title': ''}):
        with pytest.raises(ValueError):
            parse_read(json.dumps(bad))


def test_her_day_lasts_one_date_and_follows_the_clock(tmp_path):
    day = HerDay(tmp_path / 'her-day.json')
    assert day.today(DAY) is None and day.doing(DAY) is None
    day.save(SLOTS, now=DAY)
    assert day.today(DAY)['slots'] == SLOTS
    for hour, slot in {7: 'morning', 13: 'afternoon', 19: 'evening', 23: 'night'}.items():
        assert day.doing(DAY.replace(hour=hour)) == SLOTS[slot]
    assert day.doing((DAY + dt.timedelta(days=1)).replace(hour=3)) == SLOTS['night']  # Still that day's night.
    assert HerDay(tmp_path / 'her-day.json').today(DAY + dt.timedelta(days=1)) is None


@pytest.mark.asyncio
async def test_planning_her_day_adds_a_real_article_to_share_once_a_day(app):
    make_owner(app)
    article = {'title': 'Why lo-fi helps focus', 'url': 'https://example.org/lofi', 'gist': 'Steady beats lower distraction.'}
    app._hermes.complete_once = AsyncMock(side_effect=[json.dumps(SLOTS), json.dumps(article)])
    await app._plan_day()
    await app._plan_day()  # Same day: nothing new.
    assert app._hermes.complete_once.await_count == 2
    assert app._day.today()['slots'] == SLOTS
    share = [i for i in app._agenda.open() if i['kind'] == 'share']
    assert len(share) == 1 and 'Why lo-fi helps focus' in share[0]['text']
    assert share[0]['source'] == 'article:https://example.org/lofi'
    assert json.loads(app._context_text())['inner_state']['doing'] in SLOTS.values()


@pytest.mark.asyncio
async def test_no_article_when_daily_read_is_off(app):
    app._config['companion'] = {**app._config.get('companion', {}), 'daily_read': False}
    app._hermes.complete_once = AsyncMock(return_value=json.dumps(SLOTS))
    await app._plan_day()
    assert app._hermes.complete_once.await_count == 1 and app._agenda.open() == []
