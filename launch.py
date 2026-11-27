"""Desktop launcher: one companion process, owned local backend, no terminal required."""
from pathlib import Path
import fcntl
import json
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from desktop.activation import activation_path, request_activation
from brain.updates import RESTART_CODE

ROOT = Path(__file__).resolve().parent


def status(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/status', timeout=1) as response:
            return json.load(response)
    except (OSError, URLError, ValueError):
        return None


def onboarding(port):
    """The backend's first-run state: {'completed': bool, 'has_model': bool, ...} or None."""
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/onboarding', timeout=2) as response:
            return json.load(response)
    except (OSError, URLError, ValueError):
        return None


def main():
    from brain.config import load_config
    config = load_config(ROOT)
    port = config.get('ui', {}).get('port', 8000)
    data_dir=ROOT/'.chassie';data_dir.mkdir(exist_ok=True)
    lock=(data_dir/'launcher.lock').open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        if request_activation(activation_path(ROOT)): return 0
        print('Chassie is already running but could not be shown. Quit Chassie from the tray and reopen it.',file=sys.stderr)
        return 1
    backend=None
    log=(data_dir/'launcher.log').open('a',buffering=1)
    try:
        existing=status(port)
        if existing is not None and (existing.get('application')!='chassie' or existing.get('protocol')!=2):
            raise RuntimeError(f'Port {port} is occupied by an older backend or another application. Stop it before opening Chassie.')
        if existing is None:
            backend=subprocess.Popen([sys.executable,str(ROOT/'start.py'),'--text'],cwd=ROOT,stdout=log,stderr=log)
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if backend.poll() is not None:raise RuntimeError('Chassie backend stopped. See .chassie/launcher.log.')
                if (status(port) or {}).get('protocol')==2:break
                time.sleep(.2)
            else:raise RuntimeError('Chassie backend did not start within 20 seconds. See .chassie/launcher.log.')
        env=os.environ.copy()
        if sys.platform.startswith('linux'):env['QT_QPA_PLATFORM']='xcb'
        setup=onboarding(port) or {}
        if not setup.get('completed') or not setup.get('has_model'):
            # First run (or every model was removed): walk the person through setup,
            # including adding a Live2D model, instead of failing with a dialog.
            code=subprocess.call([sys.executable,'-m','desktop.onboarding','--url',f'http://127.0.0.1:{port}/onboarding'],
                                 cwd=ROOT,env=env,stdout=log,stderr=log)
            if code!=0:return 0  # Closed before finishing: nothing to show yet.
            if not (onboarding(port) or {}).get('has_model'):
                raise RuntimeError('Chassie still has no Live2D model. Open Chassie again to add one.')
        code=subprocess.call([sys.executable,'-m','desktop','--endpoint',f'ws://127.0.0.1:{port}/ws'],cwd=ROOT,env=env,stdout=log,stderr=log)
        if code==RESTART_CODE:return code  # Updated from Settings: start again after cleanup below.
        if code>0:raise RuntimeError("Chassie's avatar could not start or stopped unexpectedly. See .chassie/launcher.log.")
        return code
    except Exception as exc:
        print(str(exc),file=log)
        from PySide6.QtWidgets import QApplication,QMessageBox
        os.environ.setdefault('QT_QPA_PLATFORM','xcb')
        app=QApplication.instance() or QApplication(['Chassie'])
        QMessageBox.critical(None,'Unable to open Chassie',str(exc))
        return 1
    finally:
        if backend and backend.poll() is None:
            backend.terminate()
            try:backend.wait(timeout=10)
            except subprocess.TimeoutExpired:backend.kill();backend.wait()
        log.close();lock.close()


if __name__=='__main__':
    code=main()
    if code==RESTART_CODE:os.execv(sys.executable,[sys.executable,str(ROOT/'launch.py')])
    raise SystemExit(code)
