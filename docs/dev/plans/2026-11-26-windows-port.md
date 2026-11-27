# Windows Port Plan

> For agentic workers: one phase per session, test first, keep diffs minimal (ponytail). Nothing here is
> built yet. Linux behaviour must not change: every phase ends with the full Linux suite green.

**Goal:** Chassie installs and runs on Windows 10/11 (x86_64) with the same features as on Linux, except
barge-in without echo cancellation at first (the mic pauses while she speaks, as on Linux without PipeWire).

**Estimate:** about 1 to 1.5 weeks of work for the minimum version, 2 to 3 weeks with real echo
cancellation and a polished installer. Real-hardware test rounds on Windows set the pace.

**Testing reality (2026-11-26):** the development laptop (7 GB RAM, 25 GB free disk, hybrid RTX 2050 +
Radeon 680M) cannot comfortably host a Windows VM. Plan: GitHub Actions `windows-latest` for unit tests and
import/install smoke on every push, plus one or two sessions on a real Windows PC for overlay, audio,
camera and GPU. A VM is optional: needs ≥ 60 GB free disk, 4 GB RAM for the guest, no GPU (CPU speech
recognition, software rendering), webcam by USB redirection.

## Linux-only parts today

| Part | Files | Windows replacement |
|---|---|---|
| Installer | `scripts/setup_linux.sh`, `scripts/install_voicevox.py` | `scripts/setup_windows.ps1`; VOICEVOX Windows engine/core download |
| Screen capture (`grim`) | `vision/visual_context.py` | Qt screen grab or `mss` |
| Active app (`hyprctl`) | `vision/app_context.py`, `vision/visual_context.py` | Win32 `GetForegroundWindow` + process name (ctypes) |
| Window rules (Hyprland Lua) | `desktop/compositor.py`, `desktop/smoke.py` | Qt flags (frameless, topmost, translucent); click-through via `WS_EX_TRANSPARENT` |
| File locks (`fcntl`) | `hermes_plugin/chassie/store.py`, `mirror.py`, `launch.py`, `scripts/download_speech_asset.py` | `msvcrt.locking` behind one small helper |
| Qt platform (`xcb`) | `launch.py`, `desktop/qt_app.py` (already accepts `windows`) | Platform default on Windows |
| Echo cancellation (`pactl`) | `speech/echo_cancel.py` | None at first (mic pauses while speaking); later in-process AEC |
| Desktop entry | `scripts/install_desktop_entry.sh` | Start Menu shortcut from the installer |

## Phases

### Phase W0: CI on Windows (no Windows machine needed)
- GitHub Actions workflow: `ubuntu-latest` + `windows-latest`, Python 3.12 via uv, `pytest -q`; tests that
  need a display, audio, camera or GPU are marked and skipped on CI.
- Done when: the Windows job runs and lists what fails today (the baseline for W1).

### Phase W1: Platform layer
- New `platform_support/` (or `brain/platform.py` if small): `screen_capture()`, `active_application()`,
  `file_lock(path)`, `configure_windows(overlay)`; Linux keeps today's implementations, Windows gets the
  replacements above. Callers switch to these functions; no behaviour change on Linux.
- Tests: each function on Linux as today; Windows branches tested with mocks on Linux and for real on CI.

### Phase W2: Overlay on Windows
- Avatar and panels: frameless, topmost, translucent; click-through with `WS_EX_TRANSPARENT`; no Hyprland
  rules; DPI scaling above 100% checked.
- Needs a real Windows session: transparency, dragging, bubble menu, chat panel.

### Phase W3: Installer
- `scripts/setup_windows.ps1`: uv, Python 3.12, `.venv`, requirements, VOICEVOX (Windows build, terms prompt),
  speech/vision/memory models, Start Menu shortcut, the same `OK`/`!!` summary as the Linux setup.
- Hermes: its own `install.ps1`; the README gets Windows steps next to the Linux ones.

### Phase W4: Real-hardware test round
- Owner (or a tester) runs the installer and a 15-minute session: voice, subtitles, camera look, screen,
  reminders, memory, Telegram unaffected. Fix what the logs show.

### Phase W5 (optional): Echo cancellation on Windows
- In-process AEC (e.g. WebRTC audio processing bindings) fed with the playback signal, so barge-in works
  without PipeWire. Only if barge-in matters on Windows.

## Decided against

- Local vision description (VLM), dropped 2026-11-27: a small local model describes images worse than the
  chat model that sees them directly, and the camera is already sent only when the model decides to look.
