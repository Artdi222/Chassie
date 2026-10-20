"""Exercise real Ami generation and retained VOICEVOX without mic/camera/playback."""
import asyncio
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import wave

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tts_engine import TTSEngine


def gpu():
    result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'unavailable'


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', choices=('cpu', 'cuda'))
    parser.add_argument('--runtime')
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / 'config.yaml').read_text())
    out = ROOT / '.test-artifacts/speech'
    if args.device: out = out / args.device
    out.mkdir(parents=True, exist_ok=True)
    config['tts'] = {**config['tts'], 'engine': 'style_bert',
                     'selection_path': str(out / 'benchmark-selection.json')}
    if args.device: config['tts']['style_bert_device'] = args.device
    if args.runtime: config['tts']['style_bert_dir'] = args.runtime
    engine = TTSEngine(config)
    engine.load_model()
    primary = engine._expressive.primary
    production_timeout = primary.timeout
    primary.timeout = 30  # Measure latency first; report the configured deadline separately.
    report = {'device': primary.device, 'gpu_before_mib': gpu(), 'configured_deadline_seconds': production_timeout, 'samples': []}
    try:
        started = time.monotonic()
        print('Loading and warming Koharune Ami...', flush=True)
        await engine.select('style_bert')
        await engine._expressive._warm_task
        assert primary.ready
        report['cold_start_seconds'] = round(time.monotonic() - started, 3)
        report['gpu_ready_mib'] = gpu()
        print('Warmup: ' + str(report['cold_start_seconds']) + ' s', flush=True)
        sentence = 'こんにちは。今日も一緒にお話しできて、うれしいです。'
        cases = [(emotion, sentence) for emotion in ('neutral', 'happy', 'shy', 'sleepy', 'neutral')]
        cases.append(('neutral', '今日はどんな一日でしたか。楽しかったことも、少し大変だったことも、よかったら聞かせてください。疲れているなら、無理をしないで、ゆっくり休みましょう。私はここで待っています。'))
        for index, (emotion, text) in enumerate(cases):
            engine.begin_turn()
            started = time.monotonic()
            blocks = [block async for block in engine.synthesize_stream(text, emotion=emotion)]
            audio = np.concatenate(blocks)
            assert engine.status()['active'] == 'style_bert', 'Unexpected voice selection during Ami benchmark'
            assert np.isfinite(audio).all() and np.max(np.abs(audio)) > .001
            duration = len(audio) / config['tts']['sample_rate']
            elapsed = time.monotonic() - started
            filename = f'ami-{index + 1}-{emotion}.wav'
            with wave.open(str(out / filename), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(config['tts']['sample_rate'])
                wav.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())
            sample = {'emotion': emotion, 'characters': len(text), 'file': filename, 'seconds': round(elapsed, 3),
                      'duration': round(duration, 3), 'rtf': round(elapsed / duration, 3),
                      'meets_configured_deadline': elapsed <= production_timeout,
                      **{'worker_' + key: value for key, value in primary.last_metrics.items()}}
            report['samples'].append(sample)
            print(json.dumps(sample, ensure_ascii=False), flush=True)
        report['gpu_after_samples_mib'] = gpu()

        primary.timeout = production_timeout
        engine.begin_turn()
        started = time.monotonic()
        audio = np.concatenate([block async for block in engine.synthesize_stream(sentence, emotion='happy')])
        assert engine.status()['active'] == 'style_bert' and len(audio)
        report['production_deadline_sample'] = {'seconds': round(time.monotonic()-started, 3),
                                                 'status': engine.status()}

        # A deadline must fail without changing the selected voice or producing PCM.
        primary.timeout = .001
        engine.begin_turn()
        try:
            async for _ in engine.synthesize_stream('こんにちは。'):
                raise AssertionError('Timeout unexpectedly produced audio')
            raise AssertionError('Timeout did not fail')
        except RuntimeError:
            pass
        assert engine.status()['selected'] == 'style_bert'
        assert engine.status()['active'] is None and not primary.ready
        report['timeout_without_switch'] = engine.status()

        await engine.select('voicevox')
        engine.begin_turn()
        audio = np.concatenate([block async for block in engine.synthesize_stream('こんにちは。')])
        assert engine.status()['active'] == 'voicevox'
        assert len(audio) and np.isfinite(audio).all()
        report['manual_voicevox'] = engine.status()
        print('Timeout without switching and manual VOICEVOX verified', flush=True)

        # Cancel an active real request; this must reap the worker without switching voices.
        await primary.warmup()
        primary.timeout = 30
        process = primary._process
        task = asyncio.create_task(primary.synthesize(sentence * 5, 'happy'))
        await asyncio.sleep(.01)
        task.cancel()
        try:
            await task
            raise AssertionError('Request completed before cancellation could be tested')
        except asyncio.CancelledError:
            pass
        assert primary._process is None and process.returncode is not None
        report['real_cancel_reaped_worker'] = True
        print('Real cancellation verified', flush=True)
    finally:
        await engine.close()
        report['gpu_after_close_mib'] = gpu()
        (out / 'benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('Benchmark saved: ' + str(out / 'benchmark.json'), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
