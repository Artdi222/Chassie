# Koharune Ami TTS integration

User-authorized scope: use Koharune Ami with expressive styles and retain VOICEVOX as an immediately selectable fallback.

1. Install pinned Style-Bert-VITS2 2.5.0, CUDA PyTorch, Japanese BERT and Koharune Ami into `.chassie/style-bert`, separate from the existing runtime.
2. Add a persistent, owned subprocess with bounded JSON/WAV transport, local-only model loading, warmup, inference timeout, and kill/reap on Stop. Reuse existing decoded PCM and Japanese/English sentence protocol.
3. Map actual available Ami styles to per-sentence emotions, with moderate strength. Keep VOICEVOX Normal unchanged. Pin fallback for the remainder of a turn to avoid repeated voice changes.
4. Add a persisted TTS selector and visible engine/fallback status plus voice credits.
5. Test cancellation, failure/slow fallback, emotion changes, Japanese protocol, saved selection and browser controls. Benchmark cold/warm synthesis and inspect audio with a short neutral sample. Review changes and verify regressions. Existing VOICEVOX files are retained.
