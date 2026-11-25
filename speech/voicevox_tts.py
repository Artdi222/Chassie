"""Persistent, owned CPU speech worker; cancellation never leaves inference running."""
from __future__ import annotations
import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path
from bilingual import JAPANESE
from speech.speech_polish import clean_speech
from speech.speech_prosody import ProsodyPlanner

# One Normal style always (switching styles sounded like another person); per-sentence
# prosody in speech_prosody.py makes the delivery follow each line instead.
NORMAL_STYLE = 20
# Short, medium and long sentences: ONNX Runtime reaches full speed after a few passes.
WARMUP_PHRASES = ('こんにちは。', '今日もよろしくお願いします。', 'お疲れ様、今日は何をして過ごしていたの？ゆっくり聞かせてね。')


class VoicevoxTTS:
    def __init__(self, config):
        cfg = config['tts']
        self.root = Path(cfg.get('voicevox_dir', '.chassie/voicevox')).expanduser()
        if not self.root.is_absolute(): self.root = Path(__file__).resolve().parents[1] / self.root
        self.threads = cfg.get('cpu_threads', 2)
        self.sample_rate = cfg['sample_rate']
        self.speed = cfg.get('speed_scale', 1.0)
        if type(self.speed) not in (int, float) or not 0.5 <= self.speed <= 2.0:
            raise ValueError('VOICEVOX speed_scale must be between 0.5 and 2.0')
        self.timeout = cfg.get('timeout', 30)
        self._process = None
        self._warmed = False
        self._lock = asyncio.Lock()
        # Same Normal style always; only pitch, range, tempo and contour follow each sentence.
        self.lively = cfg.get('lively_prosody', True) is not False
        self.prosody = ProsodyPlanner()
        self.last_mouth = None  # Lip-sync keyframes of the sentence just synthesized.
        if type(self.threads) is not int or not 1 <= self.threads <= 8:
            raise ValueError('VOICEVOX cpu_threads must be between 1 and 8')

    def check_installation(self):
        paths = ('models/vvms/15.vvm', 'dict/open_jtalk_dic_utf_8-1.11/sys.dic',
                 'onnxruntime/lib/libvoicevox_onnxruntime.so.1.17.3')
        if importlib.util.find_spec('voicevox_core') is None or any(not (self.root / p).is_file() for p in paths):
            raise RuntimeError('VOICEVOX is not installed. Run .venv/bin/python scripts/install_voicevox.py.')

    async def _stop(self):
        process, self._process = self._process, None
        self._warmed = False
        if process is None: return
        if process.returncode is None:
            try: process.kill()
            except ProcessLookupError: pass
        await process.wait()

    @property
    def warm(self):
        return self._process is not None and self._process.returncode is None

    async def _ensure_process(self):
        if not self.warm:
            await self._stop()
            # Shield creation so a Stop cannot orphan a just-started native process.
            start = asyncio.create_task(asyncio.create_subprocess_exec(
                sys.executable, '-u', str(Path(__file__).with_name('voicevox_worker.py')),
                str(self.root), str(self.threads), str(self.sample_rate),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=12 * 1024 * 1024))
            try: self._process = await asyncio.shield(start)
            except asyncio.CancelledError:
                while not start.done():
                    try: await asyncio.shield(start)
                    except asyncio.CancelledError: pass
                self._process = start.result()
                raise
            ready = json.loads(await self._process.stdout.readline())
            if ready != {'ready': True}: raise RuntimeError('VOICEVOX could not start')

    async def _request(self, text, emotion):
        await self._ensure_process()
        payload = {'text': clean_speech(text), 'style': NORMAL_STYLE, 'speed': self.speed}
        if self.lively and emotion is not None:
            # The shape comes from the original text: cleaning turns "…" into a comma.
            payload['prosody'] = self.prosody.plan(text, emotion)
        request = json.dumps(payload, ensure_ascii=False)
        self._process.stdin.write((request + '\n').encode('utf-8'))
        await self._process.stdin.drain()
        line = await self._process.stdout.readline()
        result = json.loads(line)
        data = base64.b64decode(result['wav'], validate=True)
        mouth = result.get('mouth')
        self.last_mouth = mouth if isinstance(mouth, list) and len(mouth) < 20000 else None
        if not data or len(data) > 8 * 1024 * 1024: raise ValueError('Invalid VOICEVOX audio')
        return data

    async def _cleanup(self):
        # Complete cleanup even if a second Stop arrives during process teardown.
        cleanup = asyncio.create_task(self._stop())
        while not cleanup.done():
            try: await asyncio.shield(cleanup)
            except asyncio.CancelledError: pass
        cleanup.result()

    async def warmup(self):
        """Start the worker and warm ONNX Runtime, which needs a few passes to reach full speed.

        The lock is released between passes, so a real sentence queued meanwhile goes first.
        """
        for phrase in WARMUP_PHRASES:
            async with self._lock:
                if self._warmed: return
                try:
                    await asyncio.wait_for(self._request(phrase, None), timeout=self.timeout)
                except BaseException:
                    await self._cleanup()
                    raise
        self._warmed = True

    async def synthesize(self, text, emotion='neutral'):
        if not 1 <= len(text) <= 350 or not JAPANESE.search(text):
            raise RuntimeError('VOICEVOX requires a short Japanese sentence with an English translation.')
        async with self._lock:
            try:
                return await asyncio.wait_for(self._request(text, emotion), timeout=self.timeout)
            except BaseException:
                await self._cleanup()
                raise

    async def close(self):
        async with self._lock: await self._stop()
