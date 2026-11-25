import json
from unittest.mock import Mock

import launch


def with_model(root):
    (root/'model/Some').mkdir(parents=True)
    (root/'model/Some/Some.model3.json').write_text('{}')


def test_launcher_starts_and_cleans_up_only_its_own_backend(tmp_path, monkeypatch):
    (tmp_path/'config.yaml').write_text('ui:\n  port: 18765\n')
    with_model(tmp_path)
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    monkeypatch.setattr(launch,'status',Mock(side_effect=[None,{'application':'chassie','protocol':2}]))
    child=Mock();child.poll.return_value=None
    popen=Mock(return_value=child);desktop=Mock(return_value=0)
    monkeypatch.setattr(launch.subprocess,'Popen',popen)
    monkeypatch.setattr(launch.subprocess,'call',desktop)
    assert launch.main()==0
    assert popen.call_args.args[0][-1]=='--text'
    assert '--no-camera' not in popen.call_args.args[0]
    assert desktop.call_args.args[0][-1]=='ws://127.0.0.1:18765/ws'
    child.terminate.assert_called_once();child.wait.assert_called_once_with(timeout=10)


def test_launcher_preserves_an_existing_compatible_backend(tmp_path, monkeypatch):
    (tmp_path/'config.yaml').write_text('ui:\n  port: 18765\n')
    with_model(tmp_path)
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    monkeypatch.setattr(launch,'status',lambda _: {'application':'chassie','protocol':2})
    popen=Mock();monkeypatch.setattr(launch.subprocess,'Popen',popen)
    monkeypatch.setattr(launch.subprocess,'call',Mock(return_value=0))
    assert launch.main()==0
    popen.assert_not_called()


def test_second_launch_restores_desktop_without_opening_browser(tmp_path,monkeypatch):
    import fcntl
    (tmp_path/'config.yaml').write_text('ui:\n  port: 18765\n')
    (tmp_path/'.chassie').mkdir()
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    activation=Mock(return_value=True)
    monkeypatch.setattr(launch,'request_activation',activation)
    popen=Mock();monkeypatch.setattr(launch.subprocess,'Popen',popen)
    desktop=Mock();monkeypatch.setattr(launch.subprocess,'call',desktop)
    with (tmp_path/'.chassie/launcher.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert launch.main()==0
    activation.assert_called_once_with(tmp_path/'.chassie/desktop-activation.sock')
    popen.assert_not_called();desktop.assert_not_called()


def test_activation_restores_hidden_qt_window_twice(tmp_path):
    import importlib.util
    import pytest
    if any(importlib.util.find_spec(name) is None for name in ('PySide6','OpenGL','live2d')):
        pytest.skip('Requires optional desktop dependencies')
    import os,subprocess,sys
    env={**os.environ,'QT_QPA_PLATFORM':'offscreen',
         'QTWEBENGINE_CHROMIUM_FLAGS':'--disable-gpu',
         'XDG_CACHE_HOME':str(tmp_path/'cache'),'XDG_DATA_HOME':str(tmp_path/'data')}
    result=subprocess.run([sys.executable,'tests/activation_probe.py',str(tmp_path/'activate.sock')],
                          env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15)
    assert result.returncode==0,result.stdout.decode(errors='replace')[-3000:]
    assert b'DESKTOP_RESTORED_TWICE' in result.stdout


def test_launcher_explains_a_missing_model_instead_of_starting(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    (tmp_path/'config.yaml').write_text('ui:\n  port: 18765\n')
    monkeypatch.setattr(launch,'ROOT',tmp_path)
    popen=Mock();monkeypatch.setattr(launch.subprocess,'Popen',popen)
    shown=Mock();monkeypatch.setattr(QtWidgets.QMessageBox,'critical',shown)
    assert launch.main()==1
    popen.assert_not_called()
    assert 'no Live2D model yet' in shown.call_args.args[2] and 'model/README.md' in shown.call_args.args[2]
