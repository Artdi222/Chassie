# Chassie implementation and verification plan

The user's staged implementation instruction authorizes work on the evaluated direction. This ledger records actual completion separately from intended scope.

## Stage A — executable baseline and controls

1. Create isolated Python 3.12 environment and pytest configuration. Keep model dependencies lazy so text-mode and deterministic tests run without downloading models.
2. Write failing capture/mute/epoch tests, then implement separate bounded capture and transcription workers; close microphone on mute and suppress late work. Enable multilingual base model and configurable language.
3. Write failing player tests for buffered cancellation, stale generation rejection, completion race, bounded producer backpressure and output errors. Implement generation-aware playback.
4. Test Hermes timeout/malformed response/clear during in-flight work, then implement revision guards and interrupted history status.
5. Test orchestrator controls with fake devices and local fake HTTP/WebSocket gateway, then wire review/hands-free, stop, mute, clear, and UI-confirmed state independent of browser count.
6. Decode English Edge audio in memory and sentence-chunk emotion segments; test resampling, empty/failing output and cancellation. Retain no-voice fallback and honest diagnostics.

## Stage B — expression baseline (independent implementation)

Audit assets, create explicit manifest and validation tool, replace fuzzy hotkeys with expression file state, add controller-independent API, and test unknown/missing assets, neutral preservation of outfit, repeated expressions, reconnect and concurrent transitions. Integrate preview controls only after backend tests pass. Actual VTS preview remains a live check.

## Stage C — personal/guest and memory

Build explicit local profiles/memory with consent, deletion and correction; partition session histories before guest mode; wire UI controls and test no personal context in guest requests. Add face/speaker recognition only with compatible installed models and calibrated evidence; do not equate session labels with verified identity. Measure speech overlap/AEC before automatic voice barge-in.

## Stage D — screen/context and conversation behavior

Fresh timestamped observations, focus/casual modes, explicit capture and untrusted screen context. Preserve interrupted topic information. Add only supported perception and capability states; voice-triggered actions require attribution confidence.

## Stage E — standalone transparent overlay

Resolve target OS/GPU with user, choose compatible Cubism runtime, validate model manifest/bindings and alpha render. Implement bottom-right placement, hide/mute/stop and settings access, then evaluate click-through, scaling, monitor changes and VTS visual parity. Do not claim support from an empty or static avatar window.

## Checks at each stage

Red test evidence before implementation; targeted tests then full suite; Python compilation, JS syntax, browser desktop/mobile controls where applicable. Read-only live gateway health followed by a synthetic non-sensitive chat only when reachable. No user recordings or biometric enrollment generated automatically. Update verification notes with commands, counts and any external blockers. Keep commits/push outside this task unless requested.

## Progress — 2026-09-08

| Stage | Implemented and tested | Remaining gate |
| --- | --- | --- |
| A | Python 3.12 environment, bounded capture/transcription, mute epochs, cancellable device playback, revision-guarded history, review/hands-free controls, in-memory English TTS, one-sentence prefetch, actionable microphone startup after text mode, authenticated live Hermes API | Actual bilingual STT accuracy and acoustic latency/echo measurement; successful response from the configured model provider |
| B | Explicit 16-emotion manifest, acknowledged VTS transitions, original outfit preservation, derived Cubism bindings, preview inventory for connected rendering backends | User preview of candidate combinations and actual VTS comparison |
| C | Local consent-based named profiles and memory CRUD, guest context exclusion, cancellation on participant changes, anonymous multi-face presence latch | Opt-in biometric enrollment/verification, active-speaker attribution; isolation of memory/tools injected by Hermes itself |
| D | Focus/casual instruction, interrupted-topic continuation, timestamped anonymous camera observations | Explicit screen/window capture, VLM integration, verbal identity corrections, calibrated automatic interruption |
| E | Actual transparent Cubism renderer on XWayland/xcb; bottom-right placement; waist-up default; independent zoom/framing; resize/hide/recovery; backend-confirmed controls and overlay preview registration | Click delivery through to other apps, monitor/DPI transitions, Windows/native Wayland, full VTS visual/performance comparison, live audio/mouth timing |

The user confirmed Indonesian + English input, English TTS, 4 GB VRAM and 8 GB RAM. Default renderer is 30 FPS; STT uses CPU/int8 with two threads. Multiple heavy local perception models are not enabled. The model's existing texture allocation remains material even with a small overlay window.

## Verification evidence

- Full suite: `.venv/bin/python -m pytest -q` — **83 passed in 4.71 s** after the live integration exposed gateway-wrapped provider failures and regression handling was added. Earlier 79-test verification covered preview registration, prefetch, startup retry, context JSON budgeting, and TTS decoded-duration limits. Tests requiring thread wakeups, loopback sockets and Chromium were run outside the restrictive tool sandbox.
- Python `compileall` and `node --check ui/app.js` passed.
- `tools/audit_avatar.py` — 16 mapped emotions, 35 expression assets, zero errors. Four original-asset warnings: an empty costume expression, absent Expressions references, and empty EyeBlink/LipSync groups. Runtime cache supplies bindings; original assets are not overwritten.
- Real Cubism waist-up smoke: 134 parameters loaded; 71,990 nontransparent and 48,010 fully transparent pixels at 300 × 400. Screenshot `.test-artifacts/overlay-waist-up.png` inspected. Separate own-window control smoke exercised hide/show, resize and click-through flags.
- Real overlay/WebSocket integration reported 20 loaded expression IDs after a successful Draw, rendered `shy` with zero VTS calls, and removed readiness on disconnect. `.test-artifacts/overlay-preview-integration.png` inspected. This used no Hermes request, microphone or camera.
- Browser desktop/mobile tests exercised backend-confirmed mute, input mode, consent/memory, guest privacy and same-origin/loopback WebSocket access. Screenshots `.test-artifacts/controls-desktop.png` and `controls-mobile.png` inspected with mobile sidebar open. Mechanical UI audit had missing optional parser dependencies and two pre-existing style findings; it was not treated as a clean comprehensive audit.
- Real text-mode startup smoke served `/api/status` and UI on an ephemeral localhost port, with camera/microphone disabled, and shut down cleanly.
- Live Edge English synthetic sentence returned 114,624 PCM samples at 24 kHz. This checked synthesis/decode without playing audio or recording a person.
- Hermes API provisioning and service restart completed after explicit user approval. Configuration backed up, key files mode 0600; authenticated health passed and unauthenticated models returned 401; listener is 127.0.0.1:8642. Synthetic chat reached Hermes but upstream deepseek-v4-flash-free returned quota exhaustion HTTP 429 wrapped in HTTP 200 assistant text. This failure is now rejected before history/TTS; three red regression cases (quota/authentication/provider failure) passed after the fix, and an ordinary explanation mentioning that error remains a valid answer. A successful model answer remains blocked by quota/model choice, not API setup.

Red regression evidence was obtained before relevant changes: missing key header, absent prefetch before playback drain, malformed truncated context JSON, text-mode microphone not starting, and decoded TTS duration escaping its configured limit. Tests use synthetic data and fake device behavior; they do not establish biometric accuracy, physical interruption latency, or production privacy guarantees for external Hermes context.

Follow-up after the user switched Hermes to `Combo_AI`: authenticated health passed. The first synthetic request through HermesBridge returned a provider-failure notice; a single retry against chat completions timed out at the configured 30 seconds. No valid answer or model-response TTS was verified. The new provider failure has not been identified as the earlier model's quota exhaustion. No source code changes were needed for this retest.

Hyprland/Caelestia follow-up: added stable avatar application identity and scoped Lua runtime window rules for floating/pin/no_blur/no_shadow/zero border and rounding. No user shell configuration files changed. Four IPC failure/skip regression tests were added after the initial missing-module red test. Full suite: **87 passed in 4.05 s**; Python compilation passed. Real Cubism smoke verified pinned/floating/no_blur/no_shadow on the owned avatar, unpinned recovery controls, and 175,476 visible / 131,244 transparent framebuffer pixels after resize, hide/show and click-through flag changes. This did not switch the user's workspace; fullscreen game stacking is unverified. Rules must be registered again by restarting the overlay after a compositor config reload. See docs/overlay.md for reproduction.

No commit/push was requested or performed. Remaining stages above are open work, not completed features. See [Hermes setup](../../hermes-setup.md), [overlay evidence](../../overlay.md), and [evaluation](../../../evaluasi.md).

Streaming response extension is implemented and verified separately in [the streaming ledger](2026-09-08-streaming-replies.md): **138 tests passed in 5.46 s**, including actual local SSE-to-playback ordering, bounded producer backpressure, browser partial updates, microphone cancellation and guest teardown privacy. A live provider failure still prevents reporting end-to-end latency gains. English TTS-only timing remains approximately 1.03–1.50 seconds for the three tested short sentences, excluding Hermes, STT and physical playback.

Subsequent live replies succeeded and exposed a read-timeout/keepalive race, now fixed. Latest verification after per-request reasoning support: **143 passed in 7.20 s**, Python compilation passed. Authorized Hermes config changes supply matching default/alias context limits, verified with real config loaders and no network probes; the active gateway picked them up without restart. No Hermes source was modified. Preparation dropped to approximately 0.12–0.13 s on warm requests, while provider latency still varied materially. See [Hermes latency evidence, exact backup paths and all samples](../../hermes-setup.md); stable 1–2 second replies remain unproven.
