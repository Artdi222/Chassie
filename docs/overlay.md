# Optional desktop Live2D overlay

## Model studio (September 2026)

Buka **Chassie** dari menu aplikasi atau `.venv/bin/python launch.py`. Model muncul langsung; klik untuk lima tombol melengkung di kiri avatar dan seret untuk memindahkan. Menu tetap terlihat ketika tombolnya membuka panel; klik avatar lagi untuk menyembunyikan menu. Area di antara tombol transparan dan meneruskan klik. Chat terbuka di kiri atas avatar, sedangkan model/ekspresi, outfit, dan pengaturan memakai panel lokal mengambang. Posisi panel disesuaikan dengan area layar. Menu tray menyediakan kontrol pemulihan saat click-through aktif dan perintah Keluar.

Keempat paket model memakai katalog yang sama dengan web. Ekspresi dan wardrobe hanya ditawarkan jika ada pada paket; Model_4 tidak memiliki preset ekspresi. Zoom/framing tersimpan per model di `.chassie/overlay/window.json`. Renderer web dan native berbeda sehingga ukuran visual dapat disesuaikan terpisah. Launcher memakai satu backend dan satu sumber audio, mematikan mic/kamera saat mulai, serta menutup backend miliknya ketika overlay ditutup.

Instruksi manual dan detail dukungan platform di bawah tetap berguna untuk diagnosis; panel kontrol lama telah diganti oleh menu avatar dan panel studio.


The optional `desktop` entrypoint loads the real bundled Cubism `.moc3`, textures and physics through `live2d-py`, then renders into a transparent PySide6 OpenGL window. Core Chassie runs without any of these optional packages.

**Real Cubism rendering and alpha framebuffer output were verified on the current Linux XWayland/xcb session on 2026-09-08.** A bounded own-window smoke loaded 134 model parameters and rendered the actual avatar plus happy FX into a 300 × 400 PNG: 15,374 nontransparent pixels and 104,626 fully transparent pixels. The screenshot was visually inspected. A second run exercised click-through flag changes, hide/show, resize and an unavailable local endpoint, then rendered and exited successfully. This does not yet prove click delivery to other applications, native Wayland support, VTS parity, or live audio synchronization.

The pure tests validate placement, protocol state, model references and renderer commands. Missing dependencies still produce an actionable error instead of an empty avatar window.

## Installation and startup

Use the existing Python 3.12 virtual environment. Install the optional Qt/OpenGL requirements:

```bash
uv pip install --python .venv/bin/python -r requirements-overlay.txt
```

Windows installs the pinned `live2d-py==0.7.0.4` dependency through that file. For Linux, obtain the CPython 3.12 x86_64 manylinux wheel for **v0.7.0.4** from the [official release](https://github.com/EasyLive2D/live2d-py/releases/tag/v0.7.0.4), then install the downloaded local wheel with `uv pip install --python .venv/bin/python /path/to/downloaded.whl`. The project virtual environment need not contain pip. Match Python and machine architecture; do not install a Windows wheel on Linux. The [project installation instructions](https://github.com/EasyLive2D/live2d-py/blob/main/README.en.md) distinguish release wheels from PyPI availability. Building the binding from source additionally requires the official Cubism SDK under its distribution terms.

```bash
.venv/bin/python -m desktop --check
.venv/bin/python -m desktop
```

`--check` discovers optional modules only. It does not certify native imports or graphics. `--endpoint ws://127.0.0.1:8000/ws` is the default local assistant connection; remote endpoints and embedded credentials are rejected. Run the assistant separately to receive voice/animation events. Offline, the avatar returns to neutral with its mouth closed and reconnects automatically.

On Linux the current baseline is Qt `xcb` under X11 or XWayland. Native Wayland intentionally stops with a diagnostic because application-directed placement cannot be assumed. For a desktop with XWayland available:

```bash
QT_QPA_PLATFORM=xcb .venv/bin/python -m desktop
```

Windows remains untested; `xcb` has the bounded render/control evidence above, rather than a full desktop compatibility certification. An OpenGL-capable display and compositing support are required. See [Qt's transparent OpenGL window notes](https://doc.qt.io/qt-6/qopenglwidget.html#limitations-and-other-considerations) and the [binding's PySide6 example](https://github.com/EasyLive2D/live2d-py/blob/main/examples/main_pyside6.py).

## Hyprland / Caelestia

The launcher registers a narrowly matched runtime rule through `hyprctl eval` on Hyprland with its Lua configuration API (verified locally on 0.56.2). The application class is `chassie-overlay`. Separate narrow rules cover the avatar, radial controls/subtitles, and the exact chat title `Chassie — Conversation`. These transparent windows are floating and pinned, with compositor blur/shadow disabled and border/rounding set to zero. Settings and appearance panels retain their opaque surfaces. The chat shows white user bubbles on the right, dark Chassie bubbles on the left, and the composer without a header or backing panel. Press Escape while chat is focused, or click the avatar chat button again, to hide it.

Qt's always-on-top flag alone does not pin a window across workspaces. A framebuffer with alpha can still receive compositor blur, which caused the rectangular blurred background. The fix follows [Hyprland's window rules](https://wiki.hypr.land/configuring/core/rules/window-rules/). It changes no Caelestia files or global blur settings. Rules are registered once per compositor configuration session; after a Hyprland config reload, restart the overlay to register them again. Missing IPC or unsupported Lua rules display a warning in the controls while the renderer remains usable.

Close an older running overlay with Quit, then use the same launch command:

```bash
QT_QPA_PLATFORM=xcb .venv/bin/python -m desktop
```

Live verification command:

```bash
QT_QPA_PLATFORM=xcb .venv/bin/python -m desktop.smoke --emotion neutral --exercise-controls --verify-hyprland --output .test-artifacts/overlay-hyprland.png
```

The real window reported `pinned: true`, `floating: true`, `no_blur: true`, `no_shadow: true`, border/rounding zero after click-through flag changes, hide/show and resize. Recovery controls were not pinned. The real Cubism framebuffer retained both visible avatar pixels and transparent pixels. This check reads compositor properties; it does not switch the user's active workspace or certify behavior above fullscreen games.

## Behavior and controls

- Starts with a larger waist-up framing (3.3× model zoom, vertical offset −1.5), making the face clearly visible without changing the model assets. The window starts bottom-right inside the primary display's available area at 360 × 480 logical pixels; the previous position and size are restored when visible on a connected display.
- Transparent, frameless, always-on-top avatar window. The separate controls window provides show/hide, click-through, size, position reset, backend-confirmed microphone control, stop and quit.
- Zoom in/out and frame higher/lower change the model crop independently of window size; framing is saved with window geometry. Reset waist-up framing restores the default crop. Old saved positions without framing fields use the new waist-up default. Drag using the left mouse button while click-through is off. Click-through starts off so the recovery path is visible before enabling it. The tray opens controls; without a tray, controls minimize instead of disappearing.
- Uses 30 FPS by default, with `--fps 15` or `--fps 60` available. Hidden windows stop scheduling paint updates. Existing five 4096² textures alone occupy approximately 320 MiB as RGBA on the GPU before mipmaps and renderer buffers; small window size does not shrink those source textures. Measure total memory and frame time on the 4 GB VRAM / 8 GB RAM target before enabling additional local models.
- Emotion and FX use the same candidate file manifest as VTS. Native Cubism expression mixing is used, with only owned expressions removed at neutral; outfit expressions are not reset. VTS tracking tuning, saved outfits and physics overrides from `.vtube.json` are not yet imported. The native default can therefore look different from VTS.
- A runtime `.model3.json` is derived under `.chassie/overlay/` with relative references to original files plus explicit EyeBlink, LipSync and expression entries. Original model files and rig IDs remain untouched; no texture copies or image placeholders are generated. The empty costume expression is excluded.

## Local wire protocol

The desktop consumes messages from the existing assistant WebSocket:

```json
{"type":"avatar_state","emotion":"happy","mouth":0.6,"generation":7,"status":"speaking"}
{"type":"settings","mic_enabled":true,"capture_paused":false,"input_mode":"review"}
```

Only nondecreasing integer generations update the character. Invalid emotions and nonfinite mouth values are rejected. Mouth values clamp to 0–1 and expire after 750 ms without a new frame so the mouth cannot freeze open on a stalled connection. Disconnect resets generation, emotion and microphone knowledge; a restarted assistant may start counting from zero.

Controls send `{"type":"stop"}` or `{"type":"set_mic","enabled":false}`. The mute button updates only from server settings; it does not claim the microphone changed just because a command was sent. A nonessential `{"type":"hello","client":"overlay"}` identifies the connection.

## Reproducing the bounded graphics smoke

The project environment now contains PySide6 6.11.2, PyOpenGL 3.1.10 and live2d-py 0.7.0.4. The Linux wheel came from the pinned official release (the project currently redirects to EasyLive2D/relive2d), with SHA256 verified against GitHub release metadata:

`ad93059d48959daf7a4025e6d8a4de97e29bf7ca088c6dc4cab7e809223c9b1a`

```bash
QT_QPA_PLATFORM=xcb .venv/bin/python -m desktop.smoke --output .test-artifacts/overlay-smoke.png
QT_QPA_PLATFORM=xcb .venv/bin/python -m desktop.smoke --output .test-artifacts/overlay-controls-smoke.png --exercise-controls
```

Each smoke opens only its own avatar window, captures its own framebuffer after roughly 3.5 seconds, then quits; there is a 10-second watchdog. It never captures the full desktop or accesses microphone/camera. The controls variant deliberately uses a closed local endpoint and returns neutral on disconnect. Screenshots are local test artifacts, not replacement avatar assets.

## Verification still required on the target device

1. Compare the verified rendered avatar against VTS using the same expression sequence; verify compositor appearance over actual desktop backgrounds.
2. Test alpha edges against light/dark desktop backgrounds, clipping, physics, blink, lip-sync and all 16 emotion candidates, especially angry/curious.
3. Test drag, click-through with recovery controls, hide/show, scaling, DPI changes, display removal, reconnect and clean exit without OpenGL errors.
4. Speak/stop/mute from controls against the running assistant; verify audio cancellation and backend-confirmed microphone state.
5. Measure frame time and total memory at 15/30 FPS alongside STT and normal desktop apps. Renderer parity and resource suitability remain pending until those measurements exist.

Pinned API reference: [v0.7.0.4 high-level model wrapper](https://github.com/EasyLive2D/live2d-py/blob/v0.7.0.4/package/live2d/v3/lapp_model.py). No Cubism binaries are vendored in this repository.

### Reopening the application

Clicking the Chassie application icon while the desktop is already running restores and raises its existing avatar, including when hidden. It does not open the web studio or start another backend. Use **Open web studio** from the tray when you want the browser, and **Quit Chassie** to fully exit. After updating an older running launcher that opens the browser on a second click, choose **Quit Chassie** once and reopen the application.
