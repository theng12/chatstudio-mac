# Changelog — Chat Studio KH

All notable changes to Chat Studio KH are documented here.

Versioning follows [Semantic Versioning](https://semver.org/) with this project-specific interpretation:

- **MAJOR** (1.x.x → 2.x.x) — breaking change. Re-install required.
- **MINOR** (1.1.x → 1.2.x) — new feature / new model family. Re-install to pick up new Python deps.
- **PATCH** (1.2.0 → 1.2.1) — bugfix / UI tweak / catalog entry within an existing family. **Just run Update** from the Pinokio sidebar.

---

## [1.6.0] — 2026-06-26

### Added

- Three more cloud providers (free models verified against each one's live model list):
  - **Hugging Face Router** — `router.huggingface.co/v1`; **reuses your saved Hugging Face token** automatically (leave the key field blank).
  - **SambaNova** — `api.sambanova.ai/v1`.
  - **GitHub Models** — `models.github.ai/inference` (free with a fine-grained GitHub PAT that has Models read).
- Each provider shows a **Get key ↗** link to its signup/key page; env overrides `CHATSTUDIO_HFROUTER_API_KEY` / `CHATSTUDIO_SAMBANOVA_API_KEY` / `CHATSTUDIO_GITHUB_API_KEY` documented in `ENVIRONMENT`.

## [1.5.0] — 2026-06-25

### Added

- **Paid cloud models — opt-in per provider.** Each provider's paid flagship models stay hidden until you flip **Enable paid models** for that provider in **Settings → Cloud providers**. The chat route also rejects paid models until enabled (HTTP 403), so nothing bills you by accident.
  - OpenRouter: GPT-4o, GPT-4.1, Claude Sonnet 4.6, Claude Opus 4.8, Gemini 2.5 Pro, DeepSeek R1, Grok 4.3.
  - Google Gemini: Gemini 2.5 Pro.
  - Groq / Cerebras / NVIDIA: no separate paid list — their paid tiers just lift rate limits on the same (free-listed) models.
- Each provider already shows a **Get key ↗** link to its API-key page (OpenRouter, NVIDIA, Groq, Cerebras, Gemini).

## [1.4.0] — 2026-06-25

### Added

- **Cloud providers** — chat with hosted models over OpenAI-compatible APIs alongside local MLX. Add a key in **Settings → Cloud providers** (or via `CHATSTUDIO_<PROVIDER>_API_KEY` in `ENVIRONMENT`); cloud models then appear in the Chat dropdown and stream like local ones. Providers: **OpenRouter**, **NVIDIA NIM**, **Groq**, **Cerebras**, **Google Gemini**. Adding a provider is a pure data entry in `providers.py` (base URL + key env var + curated model list); the UI picks it up automatically via `GET /api/providers`.

> Model ids drift over time — if a cloud model errors, check the provider's current model list and update `providers.py`.

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
