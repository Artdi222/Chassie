import json
from pathlib import Path

import pytest

from desktop.state import OverlayState, Rect, bottom_right, fit_to_screens, validate_endpoint


def test_bottom_right_uses_available_work_area_and_negative_monitors():
    assert bottom_right(Rect(0, 0, 1920, 1040), 360, 480) == Rect(1544, 544, 360, 480)
    assert bottom_right(Rect(-1920, 0, 1920, 1040), 360, 480).x == -376


def test_removed_monitor_restores_visible_position_and_small_screen_fits():
    screen = Rect(0, 0, 800, 600)
    assert fit_to_screens(Rect(-1500, 20, 360, 480), [screen]) == bottom_right(screen, 360, 480)
    result = bottom_right(Rect(0, 0, 240, 320), 360, 480)
    assert result.x >= 0 and result.y >= 0
    assert result.x + result.width <= 240 and result.y + result.height <= 320


def test_stale_generation_and_invalid_audio_cannot_change_avatar():
    state = OverlayState()
    assert state.receive({"type": "avatar_state", "emotion": "happy", "mouth": 0.7, "generation": 4, "status": "speaking"}, now=1)
    assert not state.receive({"type": "avatar_state", "emotion": "sad", "mouth": 1, "generation": 3, "status": "speaking"}, now=1.1)
    assert state.emotion == "happy"
    assert not state.receive({"type": "avatar_state", "emotion": "happy", "mouth": float('nan'), "generation": 5, "status": "speaking"}, now=1.2)
    assert state.mouth_at(3) == 0
    state.disconnected()
    assert state.emotion == "neutral" and state.mouth == 0
    assert state.receive({"type": "avatar_state", "emotion": "sad", "mouth": 0, "generation": 0, "status": "idle"}, now=4)


def test_only_local_ws_endpoint():
    assert validate_endpoint("ws://127.0.0.1:8000/ws")
    assert validate_endpoint("ws://[::1]:8000/ws")
    for endpoint in ["https://localhost/ws", "ws://example.com/ws", "ws://user:pass@localhost/ws"]:
        with pytest.raises(ValueError):
            validate_endpoint(endpoint)


def test_settings_ack_and_disconnection_clear_microphone_assumption():
    state = OverlayState()
    state.receive({'type': 'settings', 'mic_enabled': True}, now=0)
    assert state.mic_enabled is True
    state.receive({'type': 'settings', 'mic_enabled': 'false'}, now=1)
    assert state.mic_enabled is True
    state.disconnected()
    assert state.mic_enabled is None


def test_waist_up_framing_is_default_and_adjustments_are_bounded():
    from desktop.state import Framing
    framing = Framing()
    assert framing.zoom > 2 and framing.vertical < 0
    assert Framing.from_settings({}) == framing
    assert Framing.from_settings({'zoom': float('nan'), 'vertical': 'bad'}) == framing
    assert framing.adjust(zoom=20).zoom == 4
    assert framing.adjust(zoom=-20).zoom == 1
    assert framing.adjust(vertical=-10).vertical == -2.5
    assert Framing.from_settings({'zoom': 1, 'vertical': 0}) == Framing(1, 0)


def test_left_arc_keeps_five_separate_targets_on_screen():
    from desktop.state import left_arc
    screen=Rect(0,0,1920,1080)
    for avatar in (Rect(1500,550,400,520),Rect(0,0,300,400),Rect(400,700,400,540)):
        bubbles=left_arc(avatar,screen)
        assert len(bubbles)==5
        assert [r.y for r in bubbles]==sorted(r.y for r in bubbles)
        assert bubbles[0].x>bubbles[1].x>bubbles[2].x
        assert bubbles[2].x<bubbles[3].x<bubbles[4].x
        for i,r in enumerate(bubbles):
            assert 0<=r.x and r.x+r.width<=screen.width
            assert 0<=r.y and r.y+r.height<=screen.height
            for other in bubbles[i+1:]:
                assert r.y+r.height<=other.y or r.x+r.width<=other.x or other.x+other.width<=r.x
