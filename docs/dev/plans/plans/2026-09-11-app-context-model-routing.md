# App metadata and per-turn model routing

Requested behavior: know the active application without inspecting its GUI; use
DeepSeek V4 Flash for text and MiniMax M3 when images are attached. The user also
asked whether YOLO would accelerate vision; detector replacement is not needed
for this routing change.

1. Read the active application class through a bounded Hyprland query per turn,
   independent of screenshot capture. Omit titles and report unavailable metadata
   honestly. Clear metadata after completion, error or cancellation.
2. Select the configured text/vision model from actual request image parts. Send
   the provider explicitly because Hermes can ignore bare model overrides.
   Preserve the existing history, bilingual speech and per-message image policy.
3. Test text/image/text routing over SSE, metadata availability and lifecycle,
   disabled behavior, cancellation and existing vision/voice regressions.
4. Verify the installed Hermes override contract and document any limits of live
   provider validation. No global Hermes configuration changes are required.

Verification on September 11:

- Focused routing, app context, visual privacy, streaming, bilingual, audio and
  VOICEVOX regressions: 160 passed in 9.98 seconds. Sandbox runs stalled on asyncio
  thread wakeups; the final test run completed outside that restriction.
- The actual Hyprland lookup returned an app class without capture in 0.1964 s.
- A synthetic text request succeeded through Hermes, with first text at 11.364 s
  and completion at 11.610 s. The gateway log confirmed DeepSeek V4 Flash was used.
  This is one sample, not a before/after latency benchmark or first-audio timing.
- A synthetic solid-color image request selected MiniMax M3 free, confirmed in the
  gateway log. Both the vision auxiliary and answer provider failed with server
  errors (vision HTTP 500). Live image understanding remains blocked by the
  provider; routing has passed the local SSE regression. No real desktop/camera
  image or physical audio was used in the smoke check.
- Sanitized live evidence: `.test-artifacts/model-routing-smoke.json`.
- Restart Chassie to load the changed source and config. The running desktop and
  global Hermes configuration were not restarted or modified by this change.
