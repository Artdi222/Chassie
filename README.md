<p align="center">
  <img src="docs/assets/banner.webp" alt="Chassie: a Live2D companion who lives on your desktop" width="100%">
</p>

<h1 align="center">Chassie</h1>

<p align="center"><b>A Live2D AI companion who lives on your Linux desktop.</b><br>
She talks, sees, remembers, keeps a diary, and gets a little sulky when you work too late.</p>

<p align="center">
  [<a href="https://github.com/Artdi222/Chassie/releases/latest">Download</a>]
  [<a href="#-whats-so-special">Why Chassie</a>]
  [<a href="#-install-from-source">Install from source</a>]
  [<a href="#-roadmap">Roadmap</a>]
</p>

<p align="center">
  <a href="https://github.com/Artdi222/Chassie/releases/latest"><img src="https://img.shields.io/github/v/release/Artdi222/Chassie?style=flat&colorA=080f12&colorB=e8879c&label=release"></a>
  <img src="https://img.shields.io/badge/Linux-x86__64-FCC624?style=flat&logo=linux&logoColor=white&labelColor=080f12">
  <img src="https://img.shields.io/badge/AppImage-ready-1fa669?style=flat&logo=appimage&logoColor=white&labelColor=080f12">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white&labelColor=080f12">
  <img src="https://img.shields.io/badge/Live2D-Cubism%204-ff6f91?style=flat&labelColor=080f12">
  <img src="https://img.shields.io/badge/brain-Hermes%20Agent-d97757?style=flat&labelColor=080f12">
  <img src="https://img.shields.io/badge/voice-VOICEVOX-a3c972?style=flat&labelColor=080f12">
  <img src="https://img.shields.io/badge/memory-Obsidian-7C3AED?style=flat&logo=obsidian&logoColor=white&labelColor=080f12">
</p>

<p align="center">
  <a href="https://github.com/Artdi222/Chassie/releases/latest"><img src="https://img.shields.io/badge/Download-AppImage%20for%20Linux-e8879c?style=for-the-badge&logo=linux&logoColor=white&labelColor=080f12" alt="Download the AppImage"></a>
</p>

> [!NOTE]
> Chassie is a hobby project, built with love on CachyOS + Hyprland. She is Linux-only for now (Windows is on the
> [roadmap](#-roadmap)), and you bring your own Live2D model.

Have you ever wished the character on your screen would actually *notice* you? Say "welcome back!" when you sit down,
ask how the thing you mentioned yesterday went, remind you to drink water, and pout a little when you ignore her
for three hours?

**That is Chassie.** She lives in the corner of your desktop as a Live2D character, speaks Japanese with subtitles in
English or Indonesian, hears you through the microphone, glances through the camera when it matters, and writes
what she learns about you into a Markdown folder that **you** own and can read. Her thoughts come from whichever
language model you like, through [Hermes Agent](https://github.com/NousResearch/hermes-agent). Everything else
stays on your computer.

## ✨ What's so special?

- 🫧 **She lives on your desktop, not in a browser tab.** A transparent Live2D window that blinks, breathes,
  follows your mouse, enjoys headpats, nods while you talk, and leans toward the chat when you type.
- 🎙️ **Real conversations.** Talk or type. She answers sentence by sentence in a lively VOICEVOX voice whose
  pitch and tempo follow each feeling, with lip-sync per syllable and a speech bubble you can actually read.
- 🧠 **Any brain you like.** OpenRouter, Anthropic, OpenAI, Google, local servers… whatever Hermes supports, picked
  from a searchable list in Settings, with a cheaper model for background chores if you want.
- 📝 **A memory you can read.** She decides what is worth remembering and writes tidy notes into your own
  Obsidian-friendly folder, plus a daily diary. No hidden vector database you can never look inside.
- 💭 **A life of her own.** Moods, an agenda, things she wants to ask you about later. She may start a conversation
  when you go quiet (or never, if you prefer).
- 👀 **She can see you, politely.** Face and voice recognition run locally; camera snapshots go to the model only
  when you ask or when she decides to look. Guests pause her personal memory.
- 🪞 **She knows what she looks like.** Load any Live2D model and she describes her own appearance once, so she
  talks about her look correctly.
- 📦 **One download, no terminal.** An AppImage with a first-run window that installs her brain and voice for you,
  and a **Check setup** page that says what is missing in plain words.

## 🚀 Download

> [!TIP]
> **The easy way: the AppImage.** Download `Chassie-<version>-x86_64.AppImage` from the
> [latest release](https://github.com/Artdi222/Chassie/releases/latest), make it executable and open it:
>
> ```bash
> chmod +x Chassie-*-x86_64.AppImage && ./Chassie-*-x86_64.AppImage
> ```
>
> The first-run window does the rest: **Brain** installs Hermes (or uses yours), connects and starts it, and lets
> you pick a provider, paste its API key and test it; **Character** takes your Live2D model; **Voice** installs
> VOICEVOX once you accept its terms. Models for her eyes, ears and memory download in the background.

- 🗂️ Everything of hers lives in `~/.local/share/chassie` (`config.local.yaml`, `.chassie/`, `model/`).
- ⚡ She runs on the processor; with an NVIDIA card, **Settings → System → Check setup** offers GPU acceleration
  (about 3 GB). **Check setup** also lists anything missing in plain words.
- 🔄 Needs a desktop from 2022 or later (glibc 2.34+). **Check for updates** offers each newer AppImage.

> [!IMPORTANT]
> Bring your own Live2D model (Cubism 3 or 4, with a `.model3.json`): Chassie does not ship one. Free and paid
> models are on [BOOTH](https://booth.pm/en/search/Live2D%20model) and [nizima](https://nizima.com/en); please
> respect each model's licence.

## 🔧 Install from source

**Before you start:** a Linux PC (x86_64) with about 8 GB of RAM and 6 GB of free disk, a microphone, and
an account with an AI provider that Hermes supports (an API key). A webcam and an NVIDIA graphics
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

### STEP 3 — Give her a brain: Hermes and a language model

Chassie thinks through [Hermes Agent](https://github.com/NousResearch/hermes-agent), which runs on your PC and
talks to the language model of your choice. Install it and connect your provider:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes setup model
```

In `hermes setup model`, choose your provider (OpenRouter, OpenAI, Anthropic, Google, a local server, …), paste
its API key and pick a model. Chassie uses whatever model Hermes is set up with. [Which model?](#-which-model)

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
works; see [Her memory](#-her-memory)). Tell her memory plugin where it lives, and switch Hermes's memory to it:

```bash
mkdir -p ~/Documents/Chassie-Memory
cat > ~/.hermes/chassie.json <<EOF
{"vault_path": "$HOME/Documents/Chassie-Memory", "owner_name": "Your Name",
 "private_api_session_keys": ["chassie-owner-memory"]}
EOF
```

Put your own name in `owner_name`: every memory note she saves links to it, so in Obsidian they gather
around your own note (`People/Your Name.md`). Leave it out and the notes link to no one.

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
`Live2D model: none yet` is expected here: you add one in STEP 6.

- If you see `uv was not found` → STEP 1 again, in a new terminal.
- If you see `voice not installed: its terms were not accepted` → run the setup again and type `yes`.
- If a download fails → run the setup again. Finished parts are skipped.
- If a line starts with `!!` → do what that line says, then run the setup again.

### STEP 6 — Start her and give her a body

```bash
.venv/bin/python launch.py
```

The setup also added **Chassie** to your application menu: next time, open her from there.

The first time, a **Welcome to Chassie** window opens and walks you through setup in four short screens. On the
**Character** screen you give her a body: a Live2D model.

1. Download a Live2D **Cubism 3 or 4** model. Free ones are on [BOOTH](https://booth.pm/en/search/Live2D%20free),
   [nizima](https://nizima.com/en), the [Live2D sample models](https://www.live2d.com/en/learn/sample/) and many
   VTuber communities; VTube Studio models work too. Read the model's licence: most allow personal use, few allow
   sharing.
2. Drop the downloaded **.zip** on the window, or press **Choose .zip file** (or **Choose folder** for an unpacked
   model). No unzipping needed: Chassie finds the `.model3.json` inside, copies just that model into `model/`, and
   skips extras such as PSD artwork.
3. She appears in the preview straight away. Pick how she talks with you, then press **Meet …** (her name).

You see: the window closes and after a few seconds she appears at the bottom right of your screen and greets you.

Add more models any time: click her → **Customize** → **Add another model** (or tray → **Add a model…**).
She animates any model: lip-sync, blinking, breathing, looking at you, and emotions through the standard Cubism
face parameters (mouth form, eye smile, cheeks, brows). Models with their own expression files also show those in
**Customize**.

<details><summary>Prefer to copy the files yourself?</summary>

Unzip the model into its own folder inside `model/`, one folder per model:

```
model/
└── Hiyori/
    ├── Hiyori.model3.json
    ├── Hiyori.moc3
    └── Hiyori.2048/texture_00.png
```

</details>

**First time:** click her, open **Settings** → **People & memory** → **Introduce someone**, enter your name, tick
**Remember face** (look at the camera alone) and the consent box, and press **Remember with permission**. The first
person introduced is her owner: she remembers things about you only when it is you.

- If nothing appears → read the end of `.chassie/launcher.log`; [If something goes wrong](#-if-something-goes-wrong)
  lists the usual reasons.

## 💬 Talk to her

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

## 📱 Text her from your phone

Hermes can carry her to Telegram (or Discord, WhatsApp…): the same personality from `~/.hermes/SOUL.md` and the
same memory vault, as text.

1. Make a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. `hermes gateway setup`, choose Telegram and paste the token. Then `hermes gateway restart`.
3. Put your own Telegram user id (ask [@userinfobot](https://t.me/userinfobot)) in `~/.hermes/chassie.json`:
   `"owner_ids": {"telegram": ["<your id>"]}`. Only your private chats with the bot reach her memory; anyone
   else, and group chats, talk to her without it.

Her agenda, mood and diary live on the desktop, so they follow your desktop chats only.

## 🎀 What she can do

**Conversation**
- Replies stream sentence by sentence: the first sentence is spoken while the rest is still being written.
- Japanese voice with subtitles in **English** or **Indonesian** (**Settings → Voice & chat**). She understands
  whatever language you speak.

**Voice and body**
- One VOICEVOX voice (Mochiko-san by default; pick or download another in **Settings → Voice & chat → Her voice**) whose pitch, intonation range and tempo follow each sentence and its feeling:
  questions rise, excitement speeds up, "…" slows down.
- Lip-sync per syllable from VOICEVOX's timing (a/i/u/e/o shapes, lips close on m/b/p).
- 16 emotions with smooth crossfades; common ones have several looks.
- Nods while you talk, looks at your face, glances at the chat panel while you type, looks up while she thinks,
  follows your mouse near her, and enjoys a headpat (cursor on her head).
- Hand gestures on models that have them (DeepSeek-chan: a raised finger while thinking, hand on chest, a foxtail
  grass when she teases).

**Eyes and memory**
- Camera and screen are captured locally; a snapshot goes to the model only when you ask or she decides to look.
- Face (YuNet + ArcFace) and voice (WeSpeaker) recognition run locally. Guest privacy mode pauses her personal
  memory when someone else is in the room.
- She chooses what to remember: tidy Markdown notes per category in your memory folder
  (`_generated/chassie/<Category>/<date> <title>.md`) with an index note, recalled by local full-text and
  embedding search (multilingual-e5-small).
- A daily diary in `_generated/chassie-daily/`: what happened and what to ask about again.

## 🧰 What you need

| part | needs | notes |
|---|---|---|
| Linux | x86_64, X11 or Wayland with XWayland | Developed on CachyOS + Hyprland |
| Memory | 8 GB RAM | She ran on a laptop with 7 GB usable |
| Graphics | any OpenGL card; NVIDIA optional | With NVIDIA (4 GB is enough) her ears and memory search run on the GPU |
| Disk | about 6 GB | Python packages, models in `.chassie/` |
| Language model | any provider Hermes supports | Fast, image-capable models work best: [Which model?](#-which-model) |
| Microphone | any | PipeWire echo cancellation lets you interrupt her |
| Webcam | optional | Without it she cannot see you or recognise your face |

## 🤖 Which model?

Any model Hermes can use works, as long as it can do three things:

- **Follow her reply format.** Every reply is a few short JSON lines (Japanese speech, your subtitle, an emotion).
  Current mid-size models from the big providers do this well; small local models often break it.
- **Answer fast.** She speaks the first sentence as soon as it arrives, so a quick model feels like a conversation and
  a slow one feels like waiting. Prefer "fast"/"mini"/"flash"-class models over the largest ones.
- **Read images**, if you want her to see you or your screen. Without that, set `vision.camera_enabled` and
  `vision.screen_enabled` to `false` in `config.local.yaml`, or give her a separate `hermes.vision_model`.

She was developed with Claude Haiku 5.5. By default she uses Hermes's own model; to give her a different one than
your other Hermes chats, use **Settings → System → AI model** (searchable provider and model lists taken from
Hermes: providers you signed in to come first, camera models are limited to ones that read images; thinking effort,
API key and a **Test** button;
the key goes to Hermes's `~/.hermes/.env` and is never shown again), or set it in `config.local.yaml`:

```yaml
hermes:
  provider: "openrouter"       # a provider name Hermes knows
  text_model: "<model id>"
  vision_model: "<model id>"   # must read images
  reasoning_effort: "low"      # faster replies on models that think first
  background_model: "<cheaper model id>"  # diary, memory tidying, her day; needs provider
  price_per_million: {input: 1.0, output: 4.0}  # USD: shows the session cost in Settings > System
```

Settings → System shows her health (brain, voice, microphone, memory, camera) and how many tokens this session
used. A reply with one malformed line now skips that line instead of failing the whole reply.

## 🌸 Her personality

She is always called Chassie, but who she is, is up to you. Two places shape her:

1. **`companion.persona`** in `config.local.yaml`: a short description added to every reply she gives. This is the
   main knob. Edit it in **Settings → Voice & chat → Her personality** (saved here, used from the next reply; leave it
   empty to follow only Hermes's `SOUL.md`), or
   write it like a character note, in English:

   ```yaml
   companion:
     persona: >-
       Calm, gentle and a little shy, with a dry sense of humour. Loves rainy days and old
       video games. Teases lightly, never mean. Keep replies short and spoken.
   ```

   Restart her (tray → **Quit Chassie**, then open her again) to apply it. Without your own, she uses the neutral
   starter in `config.yaml`: warm, curious, a little playful.

2. **`~/.hermes/SOUL.md`**: Hermes's own identity file, used for everything Hermes does (also its other chats).
   Her **look** does not come from there: the first time an avatar opens on the desktop, Chassie sends one
   picture of it (only the avatar) to the vision model and keeps the description per avatar design; it is
   described again when you switch to a new avatar or its files change (Customize → How she sees herself).
   Put deeper background here if you like: her story, values, how she sees herself. Keep it consistent with the
   persona.

What stays fixed: she speaks Japanese with subtitles, talks like a companion rather than an assistant, keeps replies
short, and only mentions your screen or camera when something is worth it. Those rules live in the code
(`brain/bilingual.py`, `brain/hermes_bridge.py`) because her voice and avatar depend on them.

## 📓 Her memory

Everything she remembers is plain files on your PC, in two places.

**Your memory folder** (the `vault_path` from STEP 4, for example `~/Documents/Chassie-Memory`): what she knows
about you, readable and editable by you.

```
Chassie-Memory/
├── _generated/
│   ├── chassie/
│   │   ├── Memories.md                       index of everything below (generated)
│   │   ├── People/2026-11-24 Coffee without sugar.md
│   │   ├── Events/…   Plans/…   Technical/…   Learnings/…   Reflections/…
│   └── chassie-daily/2026-11-24.md           her diary: the day, and what to ask about again
└── (anything you write yourself)
```

- **She decides what to keep**: preferences, people in your life, plans, routines, important events, and whatever
  you ask her to remember. Each memory is one small note with a date, category and tags.
- **Your own notes count too.** Every `.md` file in the folder is searched when she needs context, so a note like
  `People/Me.md` about yourself, or `Projects.md`, becomes something she knows.
- **Fix or forget** by editing or deleting a note (or ask her: "forget that I…"). The index updates itself.
- **Recall** is local: full-text search plus a small embedding model on your PC. Only the few notes that matter for
  a message are sent to the model with it.
- **Back it up** like any folder. It is a good fit for a private git repository or a synced folder.

**`.chassie/` in her folder**: her working data. `sessions/` (your chats, so she continues where you left off),
`reminders.json`, `transcripts/` (raw material for the diary), `memory.sqlite` (profiles and face/voice templates,
never photos or recordings), and her avatar settings. Delete a file there to remove that data; delete the whole
folder to start over (re-run the setup afterwards to download her models again).

She only writes memories, chats and reminders when her owner is alone with her; conversations with guests are not
saved.

## ⚙️ Settings

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
| `hermes.provider`, `hermes.text_model`, `hermes.vision_model` | Give her her own model instead of Hermes's default (`null` follows Hermes) |
| `hermes.reasoning_effort` | `low` keeps replies fast |
| `stt.language` | The language you speak (`null` auto-detects; locking it is more accurate) |
| `stt.model`, `stt.device` | Speech recognition size (`small`) and `cuda` or `cpu` |
| `tts.translation_language` | Subtitle language, `en` or `id` |
| `tts.speed_scale`, `tts.lively_prosody` | Voice tempo, and whether intonation follows each sentence |
| `conversation.input_mode` | `review` (voice becomes a draft) or `hands_free` |
| `conversation.barge_in` | Interrupt her by speaking |
| `vision.camera_enabled`, `vision.screen_enabled` | Let her use the camera / see your screen at all |
| `vision.camera_always` | `false`: she decides when to look; `true`: a photo with every message (costly) |
| `vision.screen_always` | Attach your screen when it changed and other apps are open |
| `initiative.mode` | `normal`, `rare` or `off` |
| `companion.persona` | Her personality, added to every reply: [Her personality](#-her-personality) |
| `companion.guest_privacy` | `true` pauses personal memory while someone else is around |

## 🔄 Updating her (keeps her memory)

Her memories are in your memory folder (STEP 4), and her chats, reminders, recognised faces and downloaded models
are in `.chassie/`. Updating touches neither.

Easiest: **Settings → System → Check for updates**, then **Update and restart**. It refuses when files in the
Chassie folder were changed by hand (it lists them), and re-runs the setup when the update needs new packages.
By hand:

```bash
cd Chassie
git pull
bash scripts/setup_linux.sh
```

Quit her first (tray → **Quit Chassie**), then start her again. Your `config.local.yaml` and `model/` are kept.

## 🩹 If something goes wrong

| what you see | what to do |
|---|---|
| `[FAIL] Hermes gateway unreachable` in `.chassie/launcher.log` | Hermes is not running or the key does not match: `hermes gateway status`, then STEP 4. |
| Every reply says `Hermes model provider authentication failed` | Hermes has no valid key for its provider: `hermes setup model`. |
| `Hermes model quota or rate limit reached (HTTP 429)` | Your provider account is out of credit or rate-limited. Add credit, wait a minute. |
| Replies fail with `did not contain valid Japanese speech` | The model does not follow her reply format: pick a stronger one ([Which model?](#-which-model)). |
| She says she cannot see, or replies fail when she looks | The model cannot read images: set an image-capable `hermes.vision_model`, or set `vision.camera_enabled` and `vision.screen_enabled` to `false`. |
| She answers in text but you hear nothing | Run the setup again and type `yes` for VOICEVOX; check your speakers in your sound settings. |
| `Voice input unavailable` | The microphone could not open: pick it in your sound settings, or set `audio.input_device` in `config.local.yaml`. |
| `Chassie still has no Live2D model` | Open Chassie again and add a model on the **Character** screen. If the model is refused, the message says why (an older Cubism 2 model, or no `.model3.json` inside). |
| `Chassie's avatar could not start or stopped unexpectedly` | The end of `.chassie/launcher.log` names the reason, often a model that fails to load: try another model. |
| `Port 8000 is occupied` | Another program uses the port: quit it, or set `ui.port` in `config.local.yaml`. |
| `Chassie is already running but could not be shown` | Quit her from the tray icon and open her again. |
| She mishears what you say | Lock your language: `stt.language: "en"` (or yours) in `config.local.yaml`. |
| A dark rectangle or blur around her (Wayland) | Your compositor blurs transparent windows. On Hyprland she adds her own window rules; elsewhere, turn blur off for the window class `chassie-overlay`. See [docs/overlay.md](docs/overlay.md). |
| She talks too often or too little | **Settings → Voice & chat** → when you go quiet: normal, rare or off. |
| She remembers nothing | Check `vault_path` in `~/.hermes/chassie.json` points at an existing folder, `provider: chassie` under `memory:` in `~/.hermes/config.yaml`, and that you introduced yourself (STEP 6). |

Every part writes to `.chassie/launcher.log`. When you ask for help, attach its last lines.

## 🔒 Privacy

Everything runs on your PC except the language model's replies (unless that runs locally too). Runtime data lives in `.chassie/` (git ignores it): `sessions/`
(your chats), `reminders.json`, `transcripts/` (material for the daily diary), `memory.sqlite` (face and voice
templates, never photos or recordings) and her avatar settings. Chats, memories and reminders are saved only when
her owner is alone with her; conversations with guests are not written down. The model receives text, plus a snapshot
only for a turn that needs one.

## 🏗️ How she is built

```
 mic ─▶ speech/ (faster-whisper, VAD) ──┐                 ┌─▶ speech/ VOICEVOX ─▶ audio + lip-sync
 camera / screen ─▶ vision/ ────────────┼─▶ brain/ ───────┤
 desktop chat / web studio ─ WebSocket ─┘   │      ▲      └─▶ desktop/ avatar (Qt + live2d-py), ui/ (web)
                                            ▼      │
                                brain/hermes_bridge ─▶ Hermes gateway ─▶ your language model
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

## 🧪 Development

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m playwright install chromium-headless-shell
.venv/bin/python -m pytest -q
```

462 tests (pytest, Playwright for the web panels); the ones that render a real model run only when `model/Model_4` exists and are skipped otherwise. A tagged release (`v*`) builds the AppImage on GitHub Actions (`scripts/build_appimage.sh`).
Desktop render check: `QT_QPA_PLATFORM=xcb .venv/bin/python -m desktop.smoke --output .test-artifacts/overlay.png`.

More: [desktop overlay](docs/overlay.md), [automatic vision](docs/automatic-vision.md), [VOICEVOX](docs/voicevox.md).

## 🧭 Roadmap

- [x] **Brain**: any model Hermes supports, chosen and tested from Settings
  - [x] Personality from Hermes's `SOUL.md`, plus your own notes
  - [x] Her own agenda, moods and a daily diary
- [x] **Ears**: local speech recognition (faster-whisper), echo cancellation, voice recognition of the owner
- [x] **Mouth**: VOICEVOX with per-sentence prosody and syllable lip-sync; every VOICEVOX voice in Settings
  - [ ] Voices in other languages
- [x] **Eyes**: camera and screen on demand, local face recognition, guest privacy mode
- [x] **Body**: Live2D with 16 emotions, gestures, headpats, mouse-following; she learns what her avatar looks like
- [x] **Memory**: Markdown notes in your own folder (Obsidian), local search
- [x] **Setup**: AppImage, first-run window, Check setup, updates from Settings, optional GPU pack
- [ ] Windows
- [ ] A free sample Live2D model in the first-run window

## 💞 Similar projects

Chassie is one of many attempts to give AI characters a place in our world. Go say hi to her cousins:

- [Project AIRI](https://github.com/moeru-ai/airi): a soul container for AI waifus and VTubers (web, desktop, games)
- [OpenAmika](https://github.com/zeekk0/OpenAmika): MekaHime's AI companion Amika, open source: Live2D, real-time voice, long-term memory
- [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber): talk to any LLM through a Live2D avatar, voice in and out
- [Neuro-sama](https://www.youtube.com/@Neurosama): the AI VTuber who started the dream (not open source)

## 🙏 Acknowledgements

- [Hermes Agent](https://github.com/NousResearch/hermes-agent): her brain, tools and memory plugin host
- [VOICEVOX](https://voicevox.hiroshiba.jp/): her voice; credit `VOICEVOX:もち子(cv 明日葉よもぎ)`
- [Live2D Cubism](https://www.live2d.com/), [live2d-py](https://github.com/EasyLive2D/live2d-py) and
  [pixi-live2d-display](https://github.com/guansss/pixi-live2d-display): her body on the desktop and in the panels
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
  and [WeSpeaker](https://github.com/wenet-e2e/wespeaker): her ears
- [models.dev](https://models.dev): the provider and model catalog behind the AI model picker
- [python-appimage](https://github.com/niess/python-appimage) and [AppImage](https://appimage.org/): the download
- [Project AIRI](https://github.com/moeru-ai/airi) and [OpenAmika](https://github.com/zeekk0/OpenAmika): the companion
  projects that inspired Chassie

## ⭐ Star history

<a href="https://star-history.com/#Artdi222/Chassie&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Artdi222/Chassie&type=Date&theme=dark">
    <img alt="Star history" src="https://api.star-history.com/svg?repos=Artdi222/Chassie&type=Date" width="600">
  </picture>
</a>

## 🤝 Contributors

<a href="https://github.com/Artdi222/Chassie/graphs/contributors"><img src="https://contrib.rocks/image?repo=Artdi222/Chassie&max=100" alt="Contributors"></a>

Ideas, bug reports and pull requests are welcome. If Chassie made your desk a little less lonely, a ⭐ helps others find her.

## 📜 Licenses

Chassie's code belongs to its author. Third-party parts keep their own terms:

- **VOICEVOX** runtime and the **Mochiko-san** voice: VOICEVOX terms; credit `VOICEVOX:もち子(cv 明日葉よもぎ)`. The
  full terms are downloaded to `.chassie/voicevox/models/TERMS.txt`. Another chosen voice needs its own credit,
  `VOICEVOX:<character>`, which Settings shows under the voice; follow that character's terms too.
- **WeSpeaker** speaker model: CC BY 4.0. **multilingual-e5-small**: MIT.
- **YuNet** face detector and **ArcFace** (InsightFace buffalo_l): see `scripts/install_vision.py`; the InsightFace
  weights are for non-commercial research use.
- **MediaPipe** face landmarker (`vision/face_landmarker.task`): Apache 2.0.
- **live2d-py** and the Live2D Cubism Core: their own licences. **Your Live2D model**: its author's licence.
