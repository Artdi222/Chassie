<div align="center">

<img src="ui/public/chassie-icon.png" alt="Chassie" width="160">

# Chassie

**A Live2D companion who lives on your Linux desktop**

She talks with you by voice or text, answers in Japanese with subtitles in your language,
sees you through the camera when it matters, and remembers what you tell her.

![Platform: Linux](https://img.shields.io/badge/platform-Linux%20x86__64-FCC624?logo=linux&logoColor=black)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![Brain: Hermes Agent + Claude](https://img.shields.io/badge/brain-Hermes%20Agent%20%2B%20Claude-d97757)
![Voice: VOICEVOX](https://img.shields.io/badge/voice-VOICEVOX-a3c972)

</div>

## Install her: 7 steps

**Before you start:** a Linux PC (x86_64) with about 8 GB of RAM and 6 GB of free disk, a microphone, and
an [Anthropic API key](https://console.anthropic.com/settings/keys) for Claude. A webcam and an NVIDIA graphics
card are optional: she works without them, a bit slower and without eyes.

She was built on CachyOS with Hyprland. Other desktops work through X11 or XWayland.

### STEP 1 — Install git and uv

Open a terminal. Install `git` with your package manager:

```bash
sudo pacman -S git           # Arch, CachyOS, Manjaro
sudo apt install git         # Debian, Ubuntu, Mint
sudo dnf install git         # Fedora
```

Then `uv`, which fetches the right Python (3.12) for her:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close the terminal and open a new one.

You see: `uv --version` prints a version number.

### STEP 2 — Download Chassie

```bash
git clone https://github.com/Artdi222/Chassie.git
cd Chassie
```

You see: your prompt now ends in `Chassie`.

- If you see `destination path 'Chassie' already exists` → she is downloaded already: `cd Chassie` and go on.

### STEP 3 — Give her a brain: Hermes and Claude

Chassie thinks through [Hermes Agent](https://github.com/NousResearch/hermes-agent), which runs on your PC and
talks to Claude. Install it and give it your Anthropic key:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes setup model
```

In `hermes setup model`, choose **Anthropic** and paste your API key.

You see: `hermes --help` lists commands such as `chat`, `model` and `gateway`.

- If you see `hermes: command not found` → open a new terminal (the installer adds it to your PATH), then try again.

### STEP 4 — Connect Chassie to Hermes

Chassie talks to Hermes over a private local API that needs a key. Make one and give it to both:

```bash
key=$(openssl rand -hex 32)
mkdir -p .chassie && printf '%s' "$key" > .chassie/hermes-api-key && chmod 600 .chassie/hermes-api-key
cat >> ~/.hermes/.env <<EOF
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
API_SERVER_KEY=$key
EOF
```

Her memory is a folder of Markdown notes (it opens nicely in [Obsidian](https://obsidian.md), but any folder
works). Tell her memory plugin where it lives, and switch Hermes's memory to it:

```bash
mkdir -p ~/Documents/Chassie-Memory
cat > ~/.hermes/chassie.json <<EOF
{"vault_path": "$HOME/Documents/Chassie-Memory", "private_api_session_keys": ["chassie-owner-memory"]}
EOF
```

Open `~/.hermes/config.yaml`, find the `memory:` section and set `provider: chassie` in it. Then start Hermes as
a background service:

```bash
hermes gateway install
hermes gateway restart
```

You see: `curl -s http://127.0.0.1:8642/health` answers `{"status": "ok", ...}`.

- If `curl` says `Connection refused` → `hermes gateway status` shows why; check the four `API_SERVER_` lines in
  `~/.hermes/.env` and run `hermes gateway restart` again.

### STEP 5 — Run the setup

```bash
bash scripts/setup_linux.sh
```

Takes 5 to 20 minutes: about 4 GB of downloads (Python packages, her voice, eyes, ears and memory model). It asks
once to accept the VOICEVOX terms for her voice: type `yes` and press **Enter**.

You see at the end: `Chassie setup summary`, lines starting with `OK`, then `Done. Next:`.
A line `!! no Live2D model yet` is expected here: STEP 6 fixes it.

- If you see `uv was not found` → STEP 1 again, in a new terminal.
- If you see `voice not installed: its terms were not accepted` → run the setup again and type `yes`.
- If a download fails → run the setup again. Finished parts are skipped.
- If a line starts with `!!` → do what that line says, then run the setup again.

### STEP 6 — Give her a body: a Live2D model

Chassie does not come with a model: you choose her look. Any Live2D **Cubism 3 or 4** model works (a folder with a
`.model3.json`, a `.moc3` and textures). Free models are on [Booth](https://booth.pm/en/search/Live2D%20free),
the [Live2D sample models](https://www.live2d.com/en/learn/sample/) and many VTuber communities. Read the model's
licence: most allow personal use, few allow sharing.

Unzip it into its own folder inside `model/`:

```
model/
└── Hiyori/
    ├── Hiyori.model3.json
    ├── Hiyori.moc3
    └── Hiyori.2048/texture_00.png
```

You see: `find model -name '*.model3.json'` prints your model's file.

She animates any model: lip-sync, blinking, breathing, looking at you, and emotions through the standard Cubism
face parameters (mouth form, eye smile, cheeks, brows). Models with their own expression files also show those in
the **Model** panel.

### STEP 7 — Start her

```bash
.venv/bin/python launch.py
```

The setup also added **Chassie** to your application menu: next time, open her from there.

You see: after a few seconds she appears at the bottom right of your screen and greets you.

**First time:** click her, open **Settings** → **People & memory** → **Introduce someone**, enter your name, tick
**Remember face** (look at the camera alone) and the consent box, and press **Remember with permission**. The first
person introduced is her owner: she remembers things about you only when it is you.

- If nothing appears → read the end of `.chassie/launcher.log`; [If something goes wrong](#if-something-goes-wrong)
  lists the usual reasons.

## Talk to her

Click her to open the round menu: **chat**, **model**, **outfit**, **settings** and **stop**. Drag her to move her.
**Settings → Size −/+** makes her bigger or smaller. Her tray icon has **Open web studio** and **Quit Chassie**.

- **Type** in the chat panel, or **speak**: turn the microphone on in **Settings → Voice & chat**. In `review` mode
  what you said waits as a draft; in `hands_free` it is sent at once.
- **Interrupt her** by talking while she speaks (needs PipeWire echo cancellation; without it her mic pauses while
  she talks).
- **Ask her to look**: "look at me", "what do you think of this?", "what's on my screen?". She also decides by
  herself when a photo is worth it; pictures are not sent with every message.
- **Ask for reminders**: "remind me on Saturday at 4 to call mum" or "every morning at 8". She says it when it is
  due and you are there.
- **Earlier chats**: opening her continues your last chat. **History** in the chat panel opens or deletes older
  ones, and each finished chat is summarized so she can bring it up later.
- **When you go quiet**, she may start talking: she greets you when you open her, welcomes you back, or notices
  something new. **Settings → Voice & chat** sets it to normal, rare or off.

The **web studio** (`http://127.0.0.1:8000` while she runs) has the same chat and settings in a browser, plus a
model preview. To run only the web studio without the desktop avatar: `.venv/bin/python start.py --text`.

## What she can do

**Conversation**
- Replies stream sentence by sentence: the first sentence is spoken while the rest is still being written.
- Japanese voice with subtitles in **English** or **Indonesian** (**Settings → Voice & chat**). She understands
  whatever language you speak.

**Voice and body**
- One VOICEVOX voice (Mochiko-san) whose pitch, intonation range and tempo follow each sentence and its feeling:
  questions rise, excitement speeds up, "…" slows down.
- Lip-sync per syllable from VOICEVOX's timing (a/i/u/e/o shapes, lips close on m/b/p).
- 16 emotions with smooth crossfades; common ones have several looks.
- Nods while you talk, looks at your face, glances at the chat panel while you type, looks up while she thinks,
  follows your mouse near her, and enjoys a headpat (cursor on her head).
- Hand gestures on models that have them (DeepSeek-chan: a raised finger while thinking, hand on chest, a foxtail
  grass when she teases).

**Eyes and memory**
- Camera and screen are captured locally; a snapshot goes to Claude only when you ask or she decides to look.
- Face (YuNet + ArcFace) and voice (WeSpeaker) recognition run locally. Guest privacy mode pauses her personal
  memory when someone else is in the room.
- She chooses what to remember: tidy Markdown notes per category in your memory folder
  (`_generated/chassie/<Category>/<date> <title>.md`) with an index note, recalled by local full-text and
  embedding search (multilingual-e5-small).
- A daily diary in `_generated/chassie-daily/`: what happened and what to ask about again.

## What you need

| part | needs | notes |
|---|---|---|
| Linux | x86_64, X11 or Wayland with XWayland | Developed on CachyOS + Hyprland |
| Memory | 8 GB RAM | She ran on a laptop with 7 GB usable |
| Graphics | any OpenGL card; NVIDIA optional | With NVIDIA (4 GB is enough) her ears and memory search run on the GPU |
| Disk | about 6 GB | Python packages, models in `.chassie/` |
| Claude | an Anthropic API key | Claude Haiku 5.5 by default: a reply costs a fraction of a cent |
| Microphone | any | PipeWire echo cancellation lets you interrupt her |
| Webcam | optional | Without it she cannot see you or recognise your face |

## Settings

Defaults live in `config.yaml`. Put your own changes in **`config.local.yaml`** (create it; git ignores it), so
updates never overwrite them. Any key there replaces the same key in `config.yaml`:

```yaml
# config.local.yaml
stt:
  language: "en"              # the language you speak; null auto-detects
tts:
  translation_language: "id"  # subtitles: "en" or "id" (also in Settings)
initiative:
  mode: "rare"                # normal, rare or off
companion:
  persona: >-
    Cheerful and a little sarcastic. Loves astronomy.
```

| key | what it does |
|---|---|
| `hermes.text_model`, `hermes.vision_model` | Which Claude model she uses (her own, not Hermes's default) |
| `hermes.reasoning_effort` | `low` keeps replies fast |
| `stt.language` | The language you speak (`null` auto-detects; locking it is more accurate) |
| `stt.model`, `stt.device` | Speech recognition size (`small`) and `cuda` or `cpu` |
| `tts.translation_language` | Subtitle language, `en` or `id` |
| `tts.speed_scale`, `tts.lively_prosody` | Voice tempo, and whether intonation follows each sentence |
| `conversation.input_mode` | `review` (voice becomes a draft) or `hands_free` |
| `conversation.barge_in` | Interrupt her by speaking |
| `vision.camera_always` | `false`: she decides when to look; `true`: a photo with every message (costly) |
| `vision.screen_always` | Attach your screen when it changed and other apps are open |
| `initiative.mode` | `normal`, `rare` or `off` |
| `companion.persona` | Her personality, added to every reply |
| `companion.guest_privacy` | `true` pauses personal memory while someone else is around |

## Updating her (keeps her memory)

Her memories are in your memory folder (STEP 4), and her chats, reminders, recognised faces and downloaded models
are in `.chassie/`. Updating touches neither.

```bash
cd Chassie
git pull
bash scripts/setup_linux.sh
```

Quit her first (tray → **Quit Chassie**), then start her again. Your `config.local.yaml` and `model/` are kept.

## If something goes wrong

| what you see | what to do |
|---|---|
| `[FAIL] Hermes gateway unreachable` in `.chassie/launcher.log` | Hermes is not running or the key does not match: `hermes gateway status`, then STEP 4. |
| Every reply says `Hermes model provider authentication failed` | Hermes has no valid Anthropic key: `hermes setup model`. |
| `Hermes model quota or rate limit reached (HTTP 429)` | Your Anthropic account is out of credit or rate-limited. Add credit, wait a minute. |
| She answers in text but you hear nothing | Run the setup again and type `yes` for VOICEVOX; check your speakers in your sound settings. |
| `Voice input unavailable` | The microphone could not open: pick it in your sound settings, or set `audio.input_device` in `config.local.yaml`. |
| `Chassie has no Live2D model yet` | Put a model in `model/` (STEP 6); its folder must contain a `.model3.json`. |
| `Chassie's avatar could not start or stopped unexpectedly` | The end of `.chassie/launcher.log` names the reason, often a model that fails to load: try another model. |
| `Port 8000 is occupied` | Another program uses the port: quit it, or set `ui.port` in `config.local.yaml`. |
| `Chassie is already running but could not be shown` | Quit her from the tray icon and open her again. |
| She mishears what you say | Lock your language: `stt.language: "en"` (or yours) in `config.local.yaml`. |
| A dark rectangle or blur around her (Wayland) | Your compositor blurs transparent windows. On Hyprland she adds her own window rules; elsewhere, turn blur off for the window class `chassie-overlay`. See [docs/overlay.md](docs/overlay.md). |
| She talks too often or too little | **Settings → Voice & chat** → when you go quiet: normal, rare or off. |
| She remembers nothing | Check `vault_path` in `~/.hermes/chassie.json` points at an existing folder, `provider: chassie` under `memory:` in `~/.hermes/config.yaml`, and that you introduced yourself (STEP 7). |

Every part writes to `.chassie/launcher.log`. When you ask for help, attach its last lines.

## Privacy

Everything runs on your PC except the Claude replies. Runtime data lives in `.chassie/` (git ignores it): `sessions/`
(your chats), `reminders.json`, `transcripts/` (material for the daily diary), `memory.sqlite` (face and voice
templates, never photos or recordings) and her avatar settings. Chats, memories and reminders are saved only when
her owner is alone with her; conversations with guests are not written down. Claude receives text, plus a snapshot
only for a turn that needs one.

## How she is built

```
 mic ─▶ speech/ (faster-whisper, VAD) ──┐                 ┌─▶ speech/ VOICEVOX ─▶ audio + lip-sync
 camera / screen ─▶ vision/ ────────────┼─▶ brain/ ───────┤
 desktop chat / web studio ─ WebSocket ─┘   │      ▲      └─▶ desktop/ avatar (Qt + live2d-py), ui/ (web)
                                            ▼      │
                                brain/hermes_bridge ─▶ Hermes gateway ─▶ Claude
                                                         └─ hermes_plugin/chassie ─▶ memory folder
```

```
Chassie/
├── launch.py             desktop app: backend + avatar
├── start.py              backend only (web studio)
├── config.yaml           defaults; your changes go in config.local.yaml
├── brain/                conversation: turns, Hermes protocol, sessions, reminders, initiative, web API
├── speech/               listening (STT, voice ID, echo cancel) and speaking (VOICEVOX, prosody, playback)
├── vision/               camera, screen, faces, app context, noticing changes
├── memory/               local profiles, privacy scope, vault recall, daily diary
├── avatar/               model catalog, emotion reactions, expression manifests
├── desktop/              transparent Live2D window: motion, gaze, gestures, panels
├── ui/                   web studio and the chat/settings panels
├── hermes_plugin/        memory plugin loaded by Hermes (linked by the setup)
├── model/                your Live2D models (not in git)
├── scripts/              setup and model downloaders
├── tests/                pytest suite
└── docs/                 overlay, vision and voice notes; docs/dev/ holds design history
```

## Development

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m playwright install chromium-headless-shell
.venv/bin/python -m pytest -q
```

About 360 tests; the ones that render a real model run only when `model/Model_4` exists and are skipped otherwise.
Desktop render check: `QT_QPA_PLATFORM=xcb .venv/bin/python -m desktop.smoke --output .test-artifacts/overlay.png`.

More: [desktop overlay](docs/overlay.md), [automatic vision](docs/automatic-vision.md), [VOICEVOX](docs/voicevox.md).

## Licenses

Chassie's code belongs to its author. Third-party parts keep their own terms:

- **VOICEVOX** runtime and the **Mochiko-san** voice: VOICEVOX terms; credit `VOICEVOX:もち子(cv 明日葉よもぎ)`. The
  full terms are downloaded to `.chassie/voicevox/models/TERMS.txt`.
- **WeSpeaker** speaker model: CC BY 4.0. **multilingual-e5-small**: MIT.
- **YuNet** face detector and **ArcFace** (InsightFace buffalo_l): see `scripts/install_vision.py`; the InsightFace
  weights are for non-commercial research use.
- **MediaPipe** face landmarker (`vision/face_landmarker.task`): Apache 2.0.
- **live2d-py** and the Live2D Cubism Core: their own licences. **Your Live2D model**: its author's licence.
