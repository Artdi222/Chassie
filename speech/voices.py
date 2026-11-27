"""Every VOICEVOX voice, installed or not, from the models' own README table; packs download on request."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

MODELS_VERSION = '0.16.4'  # Same as scripts/install_voicevox.py.
DEFAULT_STYLE = 20  # Mochiko-san, Normal.
CREDIT_NAMES = {'もち子さん': 'もち子(cv 明日葉よもぎ)'}  # Credit spelling the character's terms ask for.


def catalog(root):
    """[{pack, character, style, id, installed}] in the README's order."""
    root = Path(root)
    try: text = (root / 'models/README.txt').read_text(encoding='utf-8')
    except OSError: return []
    rows = re.findall(r'^\| (\d+\.vvm) \| ([^|]+?) \| ([^|]+?) \| (\d+) \|$', text, re.M)
    return [{'pack': pack, 'character': character, 'style': style, 'id': int(style_id),
             'installed': (root / 'models/vvms' / pack).is_file()} for pack, character, style, style_id in rows]


def voice(root, style_id):
    return next((v for v in catalog(root) if v['id'] == style_id), None)


def credit(character):
    return 'VOICEVOX:' + CREDIT_NAMES.get(character, character)


def pack_sizes():
    """Exact download size of each pack from the VOICEVOX release assets (never hardcoded)."""
    url = f'https://api.github.com/repos/VOICEVOX/voicevox_vvm/releases/tags/{MODELS_VERSION}'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'chassie'}), timeout=20) as response:
        return {a['name']: a['size'] for a in json.load(response).get('assets', []) if a['name'].endswith('.vvm')}


def download(root, pack):
    """Run the official downloader into a scratch folder, then move only that pack in place."""
    root = Path(root)
    if not re.fullmatch(r'\d{1,3}\.vvm', str(pack)): raise ValueError('Unknown voice pack')
    with tempfile.TemporaryDirectory(dir=root) as scratch:
        subprocess.run([str(root / 'download'), '--only', 'models', '--models-pattern', pack, '--models-version', MODELS_VERSION,
                        '--output', scratch], input='y\n', text=True, capture_output=True, timeout=1800, check=True,
                       env={**os.environ, 'COLUMNS': '120', 'LINES': '40'})
        shutil.move(Path(scratch) / 'models/vvms' / pack, root / 'models/vvms' / pack)
    # ponytail: a failed download starts over next time; resume needs the tool to support it.
