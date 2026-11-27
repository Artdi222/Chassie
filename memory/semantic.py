"""Local semantic recall over the Obsidian vault with multilingual-e5-small.

Chunks come from the vault index rows; vectors are cached by chunk id and content hash,
so only new or edited notes are embedded. Queries take a few milliseconds on the GPU.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import threading

import numpy as np

from vision.onnx_gpu import create_session
from paths import DATA

logger = logging.getLogger('memory')
MODEL_DIR = DATA / '.chassie' / 'memory-models' / 'multilingual-e5-small'


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:24]


class SemanticIndex:
    def __init__(self, model_dir=MODEL_DIR, cache_path=None, *, prefer_gpu=True):
        from tokenizers import Tokenizer
        from vision.onnx_gpu import gpu_available
        model_dir = Path(model_dir)
        use_gpu = prefer_gpu and gpu_available()
        model = model_dir / ('model_fp16.onnx' if use_gpu else 'model_quantized.onnx')
        if not model.is_file() or not (model_dir / 'tokenizer.json').is_file():
            raise FileNotFoundError('Memory model missing. It downloads when Chassie starts; Settings → System → Check setup shows why it is missing.')
        self.tokenizer = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
        self.tokenizer.enable_truncation(512)
        self.tokenizer.enable_padding()
        self.session, self.on_gpu = create_session(model, prefer_gpu=use_gpu, gpu_mem_mb=512)
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.cache_path = Path(cache_path) if cache_path else None
        self.vectors = {}  # chunk id -> (content digest, unit vector)
        self._lock = threading.Lock()
        self._load_cache()
        logger.info('Semantic memory ready on %s', 'GPU' if self.on_gpu else 'CPU')

    def _load_cache(self):
        if not (self.cache_path and self.cache_path.is_file()):
            return
        try:
            data = np.load(self.cache_path, allow_pickle=False)
            for key, digest, vector in zip(data['ids'], data['digests'], data['vectors']):
                self.vectors[str(key)] = (str(digest), vector.astype(np.float32))
        except (OSError, ValueError, KeyError):
            self.vectors = {}

    def _save_cache(self):
        if not self.cache_path or not self.vectors:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        keys = sorted(self.vectors)
        pending = self.cache_path.with_suffix('.tmp.npz')
        np.savez(pending, ids=np.array(keys), digests=np.array([self.vectors[k][0] for k in keys]),
                 vectors=np.stack([self.vectors[k][1] for k in keys]).astype(np.float16))
        pending.replace(self.cache_path)

    def embed(self, texts, kind='passage'):
        """Unit vectors; e5 expects 'query: ' / 'passage: ' prefixes."""
        out = []
        for start in range(0, len(texts), 4):  # Long 512-token chunks: keep GPU memory small.
            batch = self.tokenizer.encode_batch([f'{kind}: {t}' for t in texts[start:start + 4]])
            ids = np.array([e.ids for e in batch], dtype=np.int64)
            mask = np.array([e.attention_mask for e in batch], dtype=np.int64)
            feeds = {'input_ids': ids, 'attention_mask': mask}
            if 'token_type_ids' in self.inputs:
                feeds['token_type_ids'] = np.zeros_like(ids)
            hidden = self.session.run(None, feeds)[0].astype(np.float32)
            pooled = (hidden * mask[..., None]).sum(1) / np.maximum(mask.sum(1, keepdims=True), 1)
            out.append(pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12))
        return np.concatenate(out) if out else np.zeros((0, 384), np.float32)

    def sync(self, rows):
        """Embed new or changed chunks; drop vectors of deleted ones."""
        with self._lock:
            wanted = {str(r['id']): (_digest(r['content']), r['content']) for r in rows}
            missing = [(k, d, c) for k, (d, c) in wanted.items() if self.vectors.get(k, ('',))[0] != d]
            removed = set(self.vectors) - set(wanted)
            for key in removed:
                del self.vectors[key]
            if missing:
                vectors = self.embed([c for _, _, c in missing])
                for (key, digest, _), vector in zip(missing, vectors):
                    self.vectors[key] = (digest, vector)
            if missing or removed:
                self._save_cache()
            return len(missing)

    def rank(self, query, rows, limit=10):
        """[(z, row)] best first: how far each chunk stands out from the whole vault.

        e5 gives even unrelated pairs a cosine near 0.8, so absolute scores are not
        comparable across queries; a z-score against all chunks is.
        """
        self.sync(rows)
        with self._lock:
            pairs = [(r, self.vectors[str(r['id'])][1]) for r in rows if str(r['id']) in self.vectors]
            if not pairs or not query.strip():
                return []
            q = self.embed([query], 'query')[0]
        scores = np.stack([v for _, v in pairs]) @ q
        z = (scores - scores.mean()) / max(float(scores.std()), 1e-6)
        order = np.argsort(-z)[:limit]
        return [(float(z[i]), pairs[i][0]) for i in order]
