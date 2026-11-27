"""Private VOICEVOX subprocess. Stdout is a bounded JSON-lines audio protocol."""
from __future__ import annotations
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech.speech_prosody import apply_contour, mouth_keyframes  # noqa: E402
from speech.voices import DEFAULT_STYLE, voice  # noqa: E402


def main():
    from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
    root = Path(sys.argv[1])
    runtime = root / 'onnxruntime/lib/libvoicevox_onnxruntime.so.1.17.3'
    with Synthesizer(Onnxruntime.load_once(filename=str(runtime)),
                     OpenJtalk(str(root / 'dict/open_jtalk_dic_utf_8-1.11')),
                     acceleration_mode='CPU', cpu_num_threads=int(sys.argv[2])) as synth:
        # One chosen style (Settings → Voice); only its pack is loaded.
        chosen = int(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_STYLE
        entry = voice(root, chosen)
        if not entry or not entry['installed']: raise RuntimeError('The chosen VOICEVOX voice is not installed')
        with VoiceModelFile.open(root / 'models/vvms' / entry['pack']) as model:
            if chosen not in {style.id for speaker in model.metas for style in speaker.styles}:
                raise RuntimeError('The chosen VOICEVOX voice style is missing')
            synth.load_voice_model(model)
        print(json.dumps({'ready': True}), flush=True)
        while line := sys.stdin.buffer.readline(8193):
            if len(line) > 8192 or not line.endswith(b'\n'): raise ValueError('Request exceeds limit')
            request = json.loads(line)
            text, style = request['text'], request['style']
            if not isinstance(text, str) or not 1 <= len(text) <= 350 or style != chosen:
                raise ValueError('Invalid speech request')
            query = synth.create_audio_query(text, style)
            speed = request.get('speed', 1.0)
            if type(speed) not in (int, float) or not 0.5 <= speed <= 2.0:
                raise ValueError('Invalid speech speed')
            query.speed_scale = float(speed)
            prosody = request.get('prosody')
            if prosody is not None:
                pitch, intonation, tempo = prosody['pitch'], prosody['intonation'], prosody['speed']
                if not (all(type(v) in (int, float) for v in (pitch, intonation, tempo))
                        and -.1 <= pitch <= .1 and .5 <= intonation <= 2 and .8 <= tempo <= 1.2):
                    raise ValueError('Invalid prosody')
                query.pitch_scale = float(pitch)
                query.intonation_scale = float(intonation)
                query.speed_scale = float(speed) * float(tempo)
                apply_contour(query.accent_phrases, prosody.get('shape'), float(prosody.get('emphasis', 0)))
            moras = [m for phrase in query.accent_phrases
                     for m in [*phrase.moras, *([phrase.pause_mora] if phrase.pause_mora else [])]]
            duration = query.pre_phoneme_length + query.post_phoneme_length + sum(
                (m['vowel_length'] + (m.get('consonant_length') or 0)) if isinstance(m, dict)
                else m.vowel_length + (m.consonant_length or 0) for m in moras)
            if duration / query.speed_scale > 60: raise ValueError('Speech exceeds duration limit')
            query.output_sampling_rate = int(sys.argv[3])
            query.output_stereo = False
            wav = synth.synthesis(query, style)
            if len(wav) > 8 * 1024 * 1024: raise ValueError('Audio exceeds limit')
            print(json.dumps({'wav': base64.b64encode(wav).decode('ascii'),
                              'mouth': mouth_keyframes(query)}), flush=True)


if __name__ == '__main__':
    main()
