# Changelog — Chat Studio KH

All notable changes to Chat Studio KH are documented here.

Versioning follows [Semantic Versioning](https://semver.org/) with this project-specific interpretation:

- **MAJOR** (1.x.x → 2.x.x) — breaking change. Re-install required.
- **MINOR** (1.1.x → 1.2.x) — new feature / new model family. Re-install to pick up new Python deps.
- **PATCH** (1.2.0 → 1.2.1) — bugfix / UI tweak / catalog entry within an existing family. **Just run Update** from the Pinokio sidebar.

---

## [1.3.0] — 2026-06-25

### Fixed

- **Chat generation crash** (`RuntimeError: There is no Stream(gpu, N) in current thread`). MLX arrays are bound to the thread that created them; the model was loaded on one thread and generation ran on another. All MLX work (load, generate, unload) now runs on a single dedicated worker thread, so the streams always match. Removed the earlier `generation_stream` monkey-patch / debug hacks.

### Added

- **On-demand model loading** for the API. `POST /v1/chat/completions` and `/api/chat/completions` now auto-load the requested model if it's cached but not loaded — a true drop-in OpenAI server (e.g. for Story Studio), no separate `/api/chat/load` needed.
- **Real server-side Stop.** Clicking Stop (or a client disconnect) now halts generation on the server within one token and frees the GPU, instead of running to `max_tokens` in the background. New `POST /api/chat/cancel`.

### Changed

- Hugging Face token now also reads `CHATSTUDIO_HF_TOKEN` / `HF_TOKEN` env vars (env overrides the UI-saved token), so the documented `ENVIRONMENT` setting actually applies to downloads and Hub search.
- Pinned `hf_xet` in requirements for Xet-backed model downloads.

> Note: CHANGELOG entries for 1.2.x were not recorded; this 1.3.0 entry follows 1.1.0 directly.

## [1.1.0] — 2026-06-24

### Added — initial release

- MLX-powered LLM chat on Apple Silicon
- Curated catalog of 19 models across 8 families (Llama, Qwen, Mistral, Gemma 4/3/2, Phi, DeepSeek)
- Streaming chat with Markdown rendering, Stop button, inline generation params
- OpenAI-compatible `/v1` API (Continue.dev, Open WebUI, etc.)
- Hugging Face Hub search for discovering non-catalog models
- Resumable downloads with live progress
- HF token settings with Test button
- Launchd background-service mode (install as startup service)
- Diagnostics panel for MLX engine health
- LAN / Tailscale IP detection for cross-device API access
