# Automatic camera, screen, and face memory

Chassie starts camera and screen capture with its backend. No browser tab, open chat panel, or activation button is required. Settings shows capture availability and face-match hints. Closing Chassie releases capture; reopening starts it again. Restart the backend after updating these files or config.

Every two seconds, the backend replaces its latest camera and screen snapshots locally in memory. A conversation turn includes images only when that message explicitly requests a visual source, such as `lihat layar aku`, `read my screen`, `lihat kameraku`, or `can you see me?`. Only the requested source is attached; ask for both to include both. Ordinary messages and subsequent follow-ups carry no new images or face observations. Both typed and microphone turns use this path. Stale or failed sources are omitted. Capture does not make unsolicited model requests while idle.

With `app_context.enabled: true`, each turn reads Hyprland application metadata within a total 250 ms subprocess budget. When Chassie owns focus, it reads the live client focus order and selects the most recently focused external application that is still mapped and not hidden. All Chassie overlay/chat/control windows are excluded by application class. The result is labeled `source: last_external_focus`, so the answer describes the app used before opening chat instead of claiming it currently has keyboard focus. Ordinary external focus still reports the current app directly. Only the app class and source flags are sent, without a screenshot, window title, document name or browser tab. This works with camera and screen capture disabled. Unsupported desktops, empty workspaces, missing external apps and failed queries remain unknown; prior lookup results are never reused. Set this option to `false` to disable app metadata.

Chassie routes requests with actual image parts to `hermes.vision_model` (`minimax/minimax-m3:free`) and text-only requests to `hermes.text_model` (`deepseek/deepseek-v4-flash`). Both currently use `hermes.provider: xKiro`, matching the locally configured provider catalog. Sending an explicit provider ensures Hermes honors the per-request model override. These settings do not change the global/CLI model. An unavailable requested image stays text-only; images never carry into the next turn. Configurations omitting these options retain `hermes.model` behavior. Provider availability and response latency are separate from successful local routing.

Request recognition uses conservative Indonesian/English phrases locally, without another model call. Merely mentioning a camera/screen, quoted examples, and negated requests do not activate it. For an unclear request, name the source and ask to look at it. Local presence checks continue to protect personal memory scope without sending face observations with ordinary messages.

On Hyprland, `grim` captures the visible GUI of the monitor containing the active window; the active application's class and title accompany it. Other Wayland desktops use `grim` for the visible desktop. X11 uses Pillow ImageGrab. This sees rendered windows, text, and controls, not hidden tabs or minimized windows. It does not click or operate applications. System capture permissions still apply.

`vision.camera_enabled`, `vision.screen_enabled`, and `vision.interval_seconds` live in `config.yaml`. To run a session without capture, use `.venv/bin/python start.py --text --no-camera --no-screen`.

## Remember a face through conversation

Face the camera alone in good light, then say or type:

- `ingat wajahku sebagai Artdi` or `remember my face as Artdi`
- `lupakan wajah Artdi` or `forget the face of Artdi`

The enrollment command requires one recent, sufficiently large face. It creates or reuses the named local profile and stores an ArcFace (InsightFace `w600k_r50`, 512-d) embedding in the existing private SQLite database. Repeating enrollment replaces that profile's template. Deleting a profile also removes its face template; forgetting a face keeps the profile and text memories. Unknown faces are not enrolled automatically.

Matching runs locally using YuNet and ArcFace through OpenCV DNN (no extra dependencies). The ArcFace weights are for non-commercial use. Commands accept natural phrasings such as “Ingat wajah aku sebagai Artdi” or “Chassie, remember my face as Artdi”, but only at the start of a message; quoted or questioning mentions never enroll. A match is an estimate, not authentication, liveness verification, or evidence that the visible person is speaking. Ambiguous matches stay unknown. Matching never selects a personal memory profile or unlocks its memories. Multiple visible faces pause personal context; failed presence checks also pause it when a personal profile is selected. Use the existing People & memories controls to confirm participants before resuming personal context.

For a fresh installation, run `.venv/bin/python scripts/install_vision.py`. Downloads go to `.chassie/vision-models`, are checked against SHA-256 hashes, and retain the model licenses. Presence detection can fall back to the bundled MediaPipe model when identity weights are missing. This implementation follows the [OpenCV face detection and recognition API](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html); thresholds are conservative application choices, not a measured accuracy guarantee for this camera.

## Image handling and provider dependency

Chassie retains only the latest capture in RAM, does not save camera photos/screenshots, and strips image payloads from its conversation history. Face enrollment stores only the local embedding. Current images and window titles are sent to the configured Hermes/model service only with an explicit visual request. The optional app-name metadata described above is sent independently on each turn and is not stored as a history entry. Hermes or its providers may retain their own request data; Chassie's local retention boundary does not govern those services.

Hermes must support image input and have a functioning vision-capable provider. Capture availability means the local camera/screen worker is healthy, not that the remote model succeeded. On the September 9 verification, both local capture sources worked and local recognition detected one face. A synthetic GUI request reached Hermes, but its vision auxiliary service and reply provider returned HTTP 500. End-to-end visual understanding therefore remains unverified until that service recovers. No real camera or desktop image was sent by the verification request.

September 11 routing verification: the gateway confirmed DeepSeek V4 Flash for a
successful synthetic text request (11.364 s to first text), and MiniMax M3 free for
a synthetic image request. The image path still failed in the vision auxiliary
(HTTP 500) and answer provider. App-name lookup worked on the actual Hyprland
desktop. The focused regression suite passed 160 tests. These results verify
selection and local behavior, not a guaranteed response speed or successful live
image understanding. See [verification details](superpowers/plans/2026-09-11-app-context-model-routing.md).

## Reply timing and mouth movement

Subtitles appear during speech. Each chat sentence appears only after the audio device finishes draining that sentence. Interrupting speech or reconnecting chat cannot reveal later, unplayed sentences. The avatar receives native Python float mouth levels from the real PCM analyzer; this avoids NumPy float32 JSON serialization failures. A native-render check confirmed mouth values of 0.0 and approximately 0.7 produce distinct avatar frames.

Speech transitions target a 400 ms sentence pause (550 ms after an ellipsis, 180 ms for an unfinished phrase). Existing audio silence and synthesis waiting time count toward this pause. Eight-millisecond edge ramps soften abrupt PCM boundaries without changing speaking speed. The next sentence is still synthesized while the current sentence plays, and Stop cancels pending transitions.
