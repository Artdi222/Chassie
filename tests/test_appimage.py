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


def test_appimage_offers_the_newer_release_download(tmp_path, monkeypatch):
    import io, json
    (tmp_path / 'VERSION').write_text('v1.0.0-23-gd6e0c8f\n')
    release = {'tag_name': 'v1.1.0', 'body': 'Brain setup', 'html_url': 'https://github.com/x/releases/v1.1.0',
               'assets': [{'name': 'Chassie-v1.1.0-x86_64.AppImage', 'browser_download_url': 'https://github.com/x/Chassie-v1.1.0-x86_64.AppImage'}]}
    monkeypatch.setattr(updates, 'urlopen', lambda request, timeout: io.BytesIO(json.dumps(release).encode()))
    status = updates.check(tmp_path)
    assert status['available'] and status['appimage'] and status['download'].endswith('.AppImage') and status['notes'] == 'Brain setup'
    with pytest.raises(ValueError, match='Download the new AppImage'): updates.apply(tmp_path)
    (tmp_path / 'VERSION').write_text('v1.1.0')
    assert not updates.check(tmp_path)['available']


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


def test_launcher_dialog_names_the_backend_error(tmp_path):
    import launch
    log = tmp_path / 'launcher.log'
    log.write_text('starting\n[ERROR] The sound library PortAudio is missing. Install it.\nTraceback ...\n')
    assert launch.last_error(log) == 'The sound library PortAudio is missing. Install it.'
    assert launch.last_error(tmp_path / 'missing.log') == ''
