"""What her current avatar looks like: described once per model design, cached, and used in every reply."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROMPT = ('Describe only what this image shows: the look of the character in it (hair colour and style, eyes, glasses or other eyewear, '
          'clothing, accessories, anything distinctive) in two or three short sentences, written in English as '
          'the character speaking about herself ("I have ..."). Ignore any other description of her appearance '
          'you may know. No name, no personality, no background.')


def fingerprint(entry):
    """Changes when the design files change (model, moc, textures); motions and expressions do not count."""
    refs = entry.data['FileReferences']
    digest = hashlib.sha256()
    for path in [Path(entry.path), *(Path(entry.root) / name for name in [refs['Moc'], *refs['Textures']])]:
        stat = path.stat()
        digest.update(f'{path.name}:{stat.st_size}:{stat.st_mtime_ns};'.encode())
    return digest.hexdigest()[:16]


class AppearanceCache:
    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        try: data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError): return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix('.tmp')
        pending.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        pending.replace(self.path)

    def get(self, model_id, design):
        item = self._load().get(model_id)
        return item['text'] if isinstance(item, dict) and item.get('fingerprint') == design else None

    def put(self, model_id, design, text):
        self._save({**self._load(), model_id: {'fingerprint': design, 'text': text}})

    def forget(self, model_id):
        data = self._load(); data.pop(model_id, None); self._save(data)
