"""AppImage behavior: a fresh, read-only install starts without voices and sets itself up from Settings."""
from unittest.mock import Mock
import pytest
from brain import updates, controls
from speech.tts_engine import TTSEngine
from test_orchestrator import app  # noqa: F401


def test_speech_waits_for_voicevox_instead_of_stopping_her(tmp_path):
    engine = TTSEngine({'tts': {'engine': 'voicevox', 'sample_rate': 24000, 'voicevox_dir': str(tmp_path)}})
    engine.load_model()  # Nothing installed: no exception, text-only until a voice is installed.
    assert not engine.is_ready() and 'not installed' in engine.status()['reason']
    engine._voicevox.check_installation = lambda: None
    engine.load_model()
    assert engine.is_ready() and engine.status()['reason'] is None


@pytest.mark.asyncio
async def test_settings_installs_voicevox_when_missing(app, tmp_path, monkeypatch):
    app._voicevox_root = tmp_path
    install = Mock(); monkeypatch.setattr(controls.install_voicevox, 'install', install)
    result = await app.handle_control({'type': 'download_voice', 'pack': '15.vvm', 'accept_terms': True})
    install.assert_called_once_with(tmp_path)
    assert result['voices'] == [] and result['terms'].startswith('Unofficial English translation')


def test_appimage_points_to_releases_instead_of_git(tmp_path):
    with pytest.raises(ValueError, match='AppImage'): updates.check(tmp_path)


def test_first_run_keeps_the_git_install_menu_entry(tmp_path, monkeypatch):
    import scripts.first_run as first_run
    entry = tmp_path / 'applications/chassie.desktop'; entry.parent.mkdir(); entry.write_text('[Desktop Entry]\nExec=python launch.py\n')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path)); monkeypatch.setenv('APPIMAGE', '/x/Chassie.AppImage')
    monkeypatch.setattr(first_run, 'DATA', tmp_path)
    first_run.menu_entry()
    assert 'launch.py' in entry.read_text()
    entry.unlink(); first_run.menu_entry()
    assert 'Exec="/x/Chassie.AppImage"' in entry.read_text() and (tmp_path / 'chassie-icon.png').is_file()
    first_run.menu_entry()  # Its own entry is refreshed (new AppImage path).
