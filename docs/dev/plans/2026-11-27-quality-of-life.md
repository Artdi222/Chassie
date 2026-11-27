# Quality-of-Life Plan

> For agentic workers: one item per session, test first, ponytail (smallest working diff), full suite green
> before claiming done. Nothing here is built yet. Ordered by value for effort.

**Goal:** everything a user needs after installing (personality, AI model, voice, updates, memory) is done
inside Chassie, without a terminal or editing files.

## Facts checked (2026-11-27)

- `hermes config set|get` is non-interactive; `hermes model` is interactive (a TUI) and cannot be driven
  from the app. Chassie already accepts its own `hermes.provider` / `text_model` / `vision_model` /
  `background_model` in `config.local.yaml`, so the app does not need Hermes's picker.
- `~/.hermes/SOUL.md` is Hermes's global identity: it shapes every Hermes chat (Telegram included), not only
  Chassie. `companion.persona` in `config.local.yaml` is Chassie's own.
- VOICEVOX: only `models/vvms/15.vvm` (66 MB, Mochiko-san, style 20) is installed; each `.vvm` pack holds a
  few characters; the official `download` tool accepts `--models-pattern`. Exact sizes come from the
  VOICEVOX release assets at runtime, never hardcoded.
- `.venv` is 5 GB, of which 2.7 GB are NVIDIA CUDA libraries (`nvidia/`), 650 MB PySide6, 430 MB onnxruntime.
- Install today is a `git clone`; updates are `git pull` plus `scripts/setup_linux.sh`.

## Q1: Tidy memory panel (small, ~½–1 day)

- Settings → People & memory: group by category (People, Events, Plans, Technical, Learnings, Reflections),
  each collapsible with a count; a search box (client-side filter); 20 per page with "Show more"; newest
  first; superseded facts hidden behind "Show replaced facts". The panel scrolls inside itself with a fixed
  header, never the whole settings page.
- Backend: `memories` items gain `category`, `date`, `importance`, `superseded` (from the plugin's `facts()`).
- Tests: payload fields; a Playwright check that 200 memories render collapsed and the search filters.

## Q2: Personality editor (small, ~1 day)

- Settings → Personality: a text area for `companion.persona` (Chassie only), saved to `config.local.yaml`
  (only that key rewritten), applied on the next reply. Preview of what she is told.
- "Advanced: Hermes identity (SOUL.md)": read-only view by default; editing needs an explicit switch with
  the warning that it changes every Hermes chat (Telegram too); a timestamped backup
  (`~/.hermes/SOUL.md.bak-<time>`) before every save; never overwritten without the backup succeeding.
- Tests: persona round-trip leaves other keys untouched; SOUL.md save writes a backup first; refused
  without the switch.

## Q3: AI model from the app (medium, ~1–2 days)

- Settings → Brain: provider list and model id for chat, vision and background work (Chassie's own keys in
  `config.local.yaml`, no Hermes change needed); "Use Hermes's default" stays the first choice.
- API key: written to `~/.hermes/.env` through `hermes config env-path` (never logged, never sent to the UI
  again; the field only shows "saved").
- "Test" button: one tiny `complete_once` request; shows the reply time or the provider's error.
- Optional: "Make this Hermes's default too" runs `hermes config set model.default …` /
  `model.provider …` after confirming.
- Tests: config written and reloaded; key never in settings payloads or logs; failed test shows the reason.

## Q4: Choose her voice (medium, ~2 days)

- Settings → Voice: list every VOICEVOX character/style from the installed packs, plus packs not yet
  downloaded with their exact size from the release assets ("Pack 3 · 2 characters · 58 MB").
- Download runs the official `download` tool with `--models-pattern` and shows progress; the VOICEVOX
  terms are shown before the first download of a pack; failed downloads resume.
- Preview button speaks one sample line. Choosing a voice changes `tts.style` (one style per chosen voice:
  emotions still change prosody only, never the style; see memory "single normal voice").
- Credit line required by VOICEVOX ("VOICEVOX: <character>") shown in Settings and the README.
- Tests: style id validated against installed packs; size shown before download; credit text follows the
  choice.

## Q5: Update from the app (medium, ~1–2 days)

- Tray and Settings → System: "Check for updates" reads the latest GitHub release (tag + notes).
- Git install: "Update" stops nothing it cannot restart: `git fetch`, refuses on local changes (shows
  them), `git pull --ff-only`, re-runs the setup's quick checks, then restarts Chassie. Memory, models and
  `config.local.yaml` are untouched (they are git-ignored).
- AppImage install (after Q6): downloads the new AppImage next to the old one, verifies its checksum,
  swaps on restart (or AppImageUpdate/zsync if adopted).
- Release notes shown before updating.
- Tests: version comparison; dirty tree refusal; no update when already latest.

## Q6: AppImage (large, ~4–7 days; possible, with limits)

- Possible: Python + PySide6/QtWebEngine + onnxruntime + faster-whisper bundle into one AppImage
  (python-appimage or linuxdeploy with a relocatable Python).
- Size: about 1.3–1.5 GB without CUDA. CUDA libraries add ~2.7 GB, so the AppImage ships CPU-only and the
  first-run window offers "Download GPU acceleration (2.7 GB)" into the user's data folder.
- Not inside the AppImage: Hermes (its own installer, launched from the first-run window), VOICEVOX voice
  packs and speech/vision/memory models (downloaded on first run: licenses and size), the Live2D model
  (user's own).
- Data moves to `~/.local/share/chassie` (config, memory state, models) so the AppImage stays read-only;
  the git install keeps working as today.
- Built by a GitHub Actions workflow on each release tag and attached to the release.
- Risks: QtWebEngine sandbox inside AppImage (may need `--no-sandbox` handling), glibc floor (build on an
  older base), GPU driver mismatch for the optional CUDA pack.

## Agreed order (owner, 2026-11-27: save Claude usage)

1. ~~Q2 light: Chassie's own persona only (skip the SOUL.md editor for now).~~ Done 2026-11-27:
   Settings → Voice & chat textarea, `set_persona` control, `brain.config.save_local_persona`.
2. ~~Q5 for git installs (check and update from GitHub releases).~~ Done 2026-11-27: `brain/updates.py`
   uses `git fetch` and tags (works for the private repo with no API token); release notes are the tag
   message; restart through exit code 75 → `launch.py` execs itself. Tray entry skipped (Settings only).
3. ~~Q1~~ (done 2026-11-27: grouped, searchable, paged panel; groups open by themselves when ≤ 20 are shown),
   then ~~Q3~~ (done 2026-11-27: Settings → System → AI model; provider list with the key variable Hermes
   reads; "Make this Hermes's default too" skipped), then ~~Q4~~ (done 2026-11-27: catalog from
   `models/README.txt`, sizes from the release assets, download into a scratch folder then move the pack;
   choosing plays a sample; download progress is a status line, no resume).
4. Windows port (`2026-11-26-windows-port.md`) and Q6 AppImage later: they cost the most tokens (no local
   Windows testing; CI build loops). Build the AppImage on GitHub Actions, not locally (no large upload).
5. ~~Q6~~ (done 2026-11-27, first cut): `paths.py` (APP = code, DATA = `CHASSIE_DATA` or the repo), so the
   AppImage keeps data in `~/.local/share/chassie`; `scripts/build_appimage.sh` (python-appimage 3.12
   manylinux_2_28, CPU onnxruntime, voicevox_core wheel bundled) and `.github/workflows/appimage.yml` (v* tag →
   release asset; manual run = build check). First run: `scripts/first_run.py` (vision/speaker/memory models,
   Hermes plugin copied not linked, menu entry); VOICEVOX installs from Settings → Voice (terms checkbox); speech
   starts without VOICEVOX (text only until installed). Not done: the "Download GPU acceleration" pack, AppImage
   self-update (Q5 AppImage), bundling PortAudio (host library).

## Suggested order (original)

Q1 → Q2 → Q3 → Q4 → Q5 (git updates) → Q6 → Q5 (AppImage updates). Q1–Q4 change only the app and help
every user at once; Q6 is the largest and is what makes "just download it" true.

## After Q6: setup for non-technical people (2026-11-27)

Done: first-run window Brain step (`brain/hermes_setup.py`: official installer stage by stage with `--json`,
shared API key, API server, memory plugin copied, gateway service started; provider/key/model picked and tested)
and Voice step (VOICEVOX with its terms); plain error dialogs (backend's `[ERROR]` line, Open log folder);
ALSA-only PortAudio built into the AppImage; Settings → System → Check setup (each part with reason and fix,
first-run download state); AppImage update check against the latest GitHub release; GPU pack (`brain/gpu_pack.py`,
DATA/gpu first on sys.path). Skipped by the owner: a bundled sample Live2D model, Windows, non-Japanese voices.
Open: the release API answers only once the repository (or a release mirror) is public.
