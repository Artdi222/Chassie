# Chassie staged implementation

Authorized by the user on 2026-09-08 after evaluation/discussion. Preserve English Edge voice; accept Indonesian and English input. Retain existing UI identity and VTS. Do not rename rig parameter IDs or overwrite model assets.

## First implementation boundary

Make the existing assistant reliable before enabling autonomous guests or migrating its renderer. Use explicit review/hands-free input mode independent of browsers; backend-confirmed microphone mute that closes capture, invalidates pending audio, and prevents late transcripts; a stop control that cancels current/pending turns without shutting the player down. Capture and transcription run separately with bounded queues. Utterances carry monotonic timestamps and capture epoch. User text and transcripts enter one ordered queue; active generations are cancellable and stale results cannot commit history or audio after clear/stop.

Playback has begin/enqueue/end/cancel operations keyed by generation, with bounded block-sized buffering and completion/failure reporting. Edge audio is decoded from memory per sentence; this does not claim token streaming or continuous streaming decode. Failed TTS preserves displayed text and reports an error. Hermes history commits only for current revisions and distinguishes interrupted responses. No raw transcripts in routine debug logs.

Approved streaming extension: consume Hermes chat SSE text incrementally, ignoring reasoning/tool events and rejecting failures. Incremental emotion-aware sentence parsing feeds a queue capped at eight text segments and one next-sentence PCM prefetch. The first complete sentence can begin playback before the response stream ends. Browser partial text uses a stable bubble ID and reconnect snapshots. Stop/guest transitions cancel both receive and playback tasks, preserve only drained speech in interrupted history, and join pending microphone/device mutations. Edge still decodes complete sentence audio in memory; incremental PCM decoding is not part of this extension.

Default input review mode, microphone enabled outside text mode, multilingual Whisper base with automatic language detection, unchanged en-US-AnaNeural output. Automatic acoustic barge-in is disabled until an echo-controlled input path is validated; explicit stop/new typed input remains available. Do not pretend VAD alone is AEC or voice identity.

## Avatar boundary

Explicit per-model expression files; query actual VTS inventory, activate/deactivate desired state, preserve outfit when emotions reset, reconcile reconnects and manual changes. All 16 emotion entries audited with preview candidates identified. Avoid fuzzy name matching. Serialize transitions. Missing assets produce actionable diagnostics; unavailable VTS does not block text/audio use.

## Following stages and integration gates

Personal/guest sessions require context separation before participation, opt-in local profiles and editable explicit memory. Recognition models must be calibrated; unknown is a valid result. Never infer verified owner from one visible face. Screen capture requires explicit region/application selection and freshness. Desktop overlay must be transparent, initially bottom-right, with visible controls and no background; OS/window-system target is still requested from the user. Renderer parity and acoustic echo behavior require actual devices. Do not fabricate completion of those stages from mock tests.
