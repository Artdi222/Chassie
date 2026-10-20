# Koharune Ami speech

Chassie supports Koharune Ami (Style-Bert-VITS2) as the primary Japanese voice with English chat/subtitles. VOICEVOX Mochiko-san and its installation stay available. In Settings → Voice choose either engine; the selection persists in `.chassie/tts-selection.json`.

The Ami worker stays loaded between sentences and warms up asynchronously when Chassie starts. Speech waits for Ami to finish loading. Voices change only through Settings → Voice; loading, errors, and timeouts never select VOICEVOX automatically. If synthesis exceeds 30 seconds or fails, chat text remains available. A new reply can retry Ami. Stop cancels active generation and kills/reaps the owned worker. Selecting VOICEVOX releases the Ami worker.

## Installation

Use `.venv/bin/python scripts/install_style_bert.py`. The default CPU installer requires Linux x64 and Python 3.12, matching this laptop. It creates `.chassie/style-bert/cpu/venv` with Style-Bert-VITS2 2.5.0, PyTorch 2.3.1+cpu, Transformers 4.44.2 and NumPy 1.26.4. PyOpenJTalk-dict 0.3.4.dev2 and Setuptools 80.9.0 are pinned because the pronunciation library still imports `pkg_resources`.

The installer downloads only Koharune Ami and Japanese BERT, with pinned Hugging Face revisions and SHA256 verification of large model weights. Large model and CPU Torch downloads can resume from saved pieces. The shared model files live under `.chassie/style-bert/{model,bert}`; the CPU runtime links to them. No speaker cloning or recording is involved. Existing `.venv` packages and `.chassie/voicevox` remain intact.

The owned worker uses local model files and disables Hugging Face downloads at runtime. Japanese pronunciation reuses VOICEVOX's local `dict/open_jtalk_dic_utf_8-1.11` through `OPEN_JTALK_DICT_DIR`, avoiding a hidden first-use dictionary download. Configuration in `config.yaml`:

```yaml
tts:
  engine: style_bert
  style_bert_dir: .chassie/style-bert/cpu
  style_bert_device: cpu
  style_bert_threads: 6
  style_bert_timeout: 30.0
  style_bert_load_timeout: 120
  voicevox_dir: .chassie/voicevox
  cpu_threads: 2  # Retained VOICEVOX setting, independent of Ami's thread count
  sample_rate: 24000
```

Both engines return bounded mono PCM through the existing 24 kHz playback path. Both voice choices remain Japanese, preserving the same response/translation protocol. `tts.engine: voicevox` also remains supported directly in config.

Optional CUDA installation uses `scripts/install_style_bert.py --device cuda`, then `style_bert_dir: .chassie/style-bert` and `style_bert_device: cuda`. CUDA inference has not been validated on this laptop; the active configuration uses the measured CPU runtime.

## Local validation

On the Ryzen 5 7535HS laptop, a 26-character Japanese sample took 4.7–5.7 seconds with two threads, 2.85–3.0 seconds with four, and 1.76–2.0 seconds with six in the comparison run. The active Ami setting uses six threads. The final production-path run measured 1.74–2.38 seconds across five short samples and 4.23 seconds for warmup with existing caches. These are local synthesis measurements, not total chat latency. An 86-character sample took 10.37 seconds when measured without the production deadline; the current 30-second deadline allows that sentence to complete with Ami.

Real-model testing produced Neutral, るんるん, ささやきB（有声） and よふかし audio through the production PCM decoder. The original real-model run verified worker cleanup on timeout and cancellation. The updated benchmark checks timeout without switching voices and manually selected VOICEVOX. `scripts/benchmark_style_bert.py --device cpu --runtime .chassie/style-bert/cpu` saves audio and metrics under `.test-artifacts/speech/cpu/`. It measures unrestricted synthesis first, then checks the production deadline and cancellation separately.

## Styles

Ami provides delivery styles, rather than a dedicated preset for every emotion. Use only actual model styles, with moderate strengths:

| Chat emotion | Ami style | Strength |
| --- | --- | --- |
| happy, excited, teasing | るんるん (cheerful) | 0.8 |
| sleepy, sad, concerned, defeated | よふかし (late-night, softer) | 0.7 |
| shy, love | ささやきB（有声） (voiced whisper) | 0.6 |
| other / neutral | Neutral | 0.8 |

Each sentence receives its own emotion; VOICEVOX continues using Mochiko-san Normal. The other available styles, ノーマル and ささやきA（無声）, are not selected automatically. Exact perceived emotion depends on the text and model.

## Attribution and sources

Style-Bert-VITS2 model: 小春音アミ (Koharune Ami). Voice source: **あみたろの声素材工房 — https://amitaro.net/**. This is litagin's speech model trained from the published corpus, not a voice recording made for Chassie.

- [Model card, styles and usage terms](https://huggingface.co/litagin/sbv2_koharune_ami)
- [Source voice terms](https://amitaro.net/voice/voice_rule/)
- [Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2)
- [VOICEVOX setup and attribution](voicevox.md)

UI credits cover Ami and the retained VOICEVOX voice. Preserve the applicable attribution when sharing generated recordings. Installer keeps `MODEL_CARD.md` and `SOURCES.json` alongside model files; worker diagnostics are in `worker.log`, without chat text logging.
