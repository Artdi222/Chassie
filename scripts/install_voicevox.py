"""Install the pinned, minimal Linux x64 VOICEVOX CPU bundle for Chassie.

Run with .venv/bin/python scripts/install_voicevox.py. Installing accepts the
standard VOICEVOX runtime/model terms; attribution and terms stay in the bundle.
"""
from pathlib import Path
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paths import DATA  # noqa: E402
DEST = DATA / '.chassie/voicevox'
CORE = '0.17.0'
BASE = f'https://github.com/VOICEVOX/voicevox_core/releases/download/{CORE}'


def install(dest=DEST):
    """Runtime, dictionary and the Mochiko-san voice into dest (also used by Settings → Voice on a fresh install)."""
    dest = Path(dest)
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        raise RuntimeError('This installer currently supports Linux x64. See docs/voicevox.md.')
    dest.mkdir(parents=True, exist_ok=True)
    required = ['dict/open_jtalk_dic_utf_8-1.11/sys.dic', 'models/vvms/15.vvm',
                'models/TERMS.txt', 'onnxruntime/lib/libvoicevox_onnxruntime.so.1.17.3']
    if any(not (dest / path).is_file() for path in required):
        downloader = dest / 'download'
        print('Downloading official VOICEVOX installer…', flush=True)
        with urllib.request.urlopen(BASE + '/download-linux-x64', timeout=60) as response:
            with downloader.open('wb') as output: shutil.copyfileobj(response, output)
        downloader.chmod(0o755)
        print('Installing CPU runtime, dictionary and Mochiko-san voice model…', flush=True)
        with (dest / 'install.log').open('w') as log:
            subprocess.run([str(downloader), '--exclude', 'c-api', '--devices', 'cpu',
                            '--models-pattern', '15.vvm', '--models-version', '0.16.4',
                            '--onnxruntime-version', '1.17.3', '--output', str(dest)],
                           input='y\n', text=True, stdout=log, stderr=log, check=True,
                           env={**os.environ, 'COLUMNS':'120', 'LINES':'40'})
    try: installed = importlib.metadata.version('voicevox-core')
    except importlib.metadata.PackageNotFoundError: installed = None
    if installed != CORE:
        wheel = BASE + f'/voicevox_core-{CORE}-cp310-abi3-manylinux_2_34_x86_64.whl'
        uv = shutil.which('uv')
        command = [uv, 'pip', 'install', '--python', sys.executable,
                   '--cache-dir', str(dest / 'pip-cache'), '--link-mode', 'copy'] if uv else [sys.executable, '-m', 'pip', 'install']
        subprocess.run([*command, wheel], check=True)


def main():
    install()
    print('VOICEVOX installed. Voice credit: VOICEVOX:もち子(cv 明日葉よもぎ)')
    print('Start Chassie normally. Speech is Japanese; chat and subtitles are English.')


if __name__ == '__main__':
    main()
