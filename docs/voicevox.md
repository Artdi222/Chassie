# VOICEVOX Mochiko-san

Chassie uses local VOICEVOX Core for Japanese speech. Input can be typed or spoken in Indonesian or English (`stt.language: null` detects microphone language). Chat and subtitles show the English translation of each Japanese sentence. Hermes generates both together; translation still needs the configured Hermes provider. Local TTS does not send text to a speech service.

Start Chassie using its existing application shortcut. No VOICEVOX editor or extra terminal command is needed during normal use. After changing engines, fully quit and reopen Chassie once.

## Installation (Linux x64, Python 3.10+)

From the project directory:

```sh
.venv/bin/python scripts/install_voicevox.py
```

The installer accepts the standard VOICEVOX runtime/model terms and keeps their files under `.chassie/voicevox`. Downloads are pinned to Core 0.17.0, VOICEVOX ONNX Runtime 1.17.3, VVM 0.16.4 (`15.vvm`), and Open JTalk dictionary 1.11. The Python SDK is installed into the interpreter used to run the script. Runtime 1.17.3 was verified with this SDK; its recommended runtime filename is newer, so Chassie selects the installed compatible library explicitly.

Only one VVM is downloaded and loaded (this official file also contains several other characters; Chassie selects only Mochiko-san). CPU inference uses two threads, preserving GPU memory for the avatar. The worker starts on the first sentence, stays warm for later replies, and exits on Stop during synthesis, timeout or backend shutdown. A restarted worker incurs loading latency again.

`tts.engine: voicevox` is the only supported engine. Speech is Japanese and replies/subtitles are English.

## Voice style and pronunciation

All replies use **Mochiko-san Normal (style 20)**, including happy, sad and thinking replies. Avatar expressions still follow each sentence independently. Speaking tempo is `tts.speed_scale: 1.0`; manual avatar expression selection remains independent of voice delivery.

The bilingual prompt asks Hermes to write foreign names, app names, initialisms and filenames as spoken kana in the Japanese speech field. For example, `VS Code` is spoken as `ブイエス・コード`, and `bilingual.py` as `バイリンガル・ドット・パイ`. The English chat and subtitle translation preserves the original spelling. These are Japanese phonetic readings; pronunciation still depends on the model supplying the correct reading.

## Response and interruption behavior

Hermes emits one JSON object per sentence pair: `emotion`, `ja`, `en`. Complete validated pairs stream into a bounded queue. Japanese reaches TTS; English reaches chat and the currently playing subtitle. Raw JSON never appears in displayed history. Invalid/missing translations fail visibly in English instead of being spoken. Short pairs are required (Japanese ≤350 characters, English ≤700); the usual reply is 1–3 pairs.

Stop cancels both the model stream and owned synthesis process. Only fully played English translations remain in interrupted conversation context. Reconnecting web/desktop clients receive the English history. Audio playback still has one owner on the backend. Sentence completion flushes the reported device latency with silence before stopping the stream, protecting sentence endings on ALSA/PipeWire hosts that return early from stop. Completed sentences are not aborted when the next sentence begins.

## Attribution and sources

Voice: **VOICEVOX:もち子(cv 明日葉よもぎ)**. The same credit appears in shared settings. Preserve this credit with shared audio samples and check the voice's terms before redistributing a product or voice assets.

- [Mochiko-san](https://voicevox.hiroshiba.jp/product/mochikosan/)
- [Voice model terms and style table](https://github.com/VOICEVOX/voicevox_vvm/tree/0.16.4)
- [Official Core usage](https://github.com/VOICEVOX/voicevox_core/blob/0.17.0/docs/guide/user/usage.md)
- [Official Core downloader](https://github.com/VOICEVOX/voicevox_core/blob/0.17.0/docs/guide/user/downloader.md)

## Local verification

On the user's 8 GB RAM / RTX 2050 laptop, CPU two-thread synthesis produced 3.30 seconds of audio in 2.89 seconds with cold loading; two subsequent samples took 1.69 and 1.19 seconds for 3.90 and 2.54 seconds of audio. The warm worker used approximately 352 MiB RSS at observation. These are individual samples, not an end-to-end latency guarantee. Hermes and translation latency are additional.

Real Indonesian and English typed inputs both produced valid Japanese/English pairs and synthesized Japanese WAVs. Native cancellation/restart passed. Samples and timing evidence are under `.test-artifacts/voicevox/` locally (not committed).
