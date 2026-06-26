# Changelog — Chat Studio KH

All notable changes to Chat Studio KH are documented here.

Versioning follows [Semantic Versioning](https://semver.org/) with this project-specific interpretation:

- **MAJOR** (1.x.x → 2.x.x) — breaking change. Re-install required.
- **MINOR** (1.1.x → 1.2.x) — new feature / new model family. Re-install to pick up new Python deps.
- **PATCH** (1.2.0 → 1.2.1) — bugfix / UI tweak / catalog entry within an existing family. **Just run Update** from the Pinokio sidebar.

---

## [1.10.0] — 2026-06-26

### Added — RAM planner: interactive memory slider + live "Best for your RAM" picks (Models tab)

The Models tab's "Your Mac" banner became an interactive **hardware planner** so you can size models to a machine you don't own yet.

- **RAM slider + numeric entry + tier presets** (8 / 16 / 24 / 32 / 48 / 64 / 128 / 256 / 512 GB). Defaults to your detected RAM; drag/type to *preview* a different Mac (e.g. plan an M3 Ultra 512 GB before buying it). A `↩ My Mac` button snaps back to detected. The chosen budget persists across reloads.
- **Live hardware fit** — per-card fit chips and the existing **RAM fit** segmented filter (All / OK / Tight / Over) are now scored **client-side** against the slider via `fitFor()`/`effectiveRam`, so they re-score instantly with no `/api/catalog` round-trip. This also fixes the "Over" filter, which previously compared against a fit state the backend never emitted.
- **✨ Best for your RAM** — surfaces the highest-quality model in each lane (overall / code / reasoning / starter) that still fits the budget. At 8 GB it favours the small models; at 64 GB+ it upgrades to 70B-class.

**Frontend-only — no new Python dependencies. A plain _Update_ from the Pinokio sidebar is enough.**

---

## [1.12.0] — 2026-06-26

### Added

- **Uninterrupted Mode (Phase 3) — Continue with fallback.** If a reply streams some text and *then* the provider drops (so the router can't silently swap mid-answer), the partial answer is kept and a **Continue with fallback →** button appears. Clicking it resumes on the next available provider — excluding the one that just broke — and appends to the same message. New `exclude_providers` field on the chat request.

## [1.11.0] — 2026-06-26

### Added

- **Uninterrupted Mode (Phase 2) — fallback order & health.** Settings now has a **Fallback order & health** panel: reorder providers with ↑/↓ (top = tried first), enable/disable each, and see a live **health badge** per provider — *online · slow · offline · rate-limited · no key*. Health is checked on launch and every 5 minutes. Local MLX + all cloud providers participate. New endpoints: `GET /api/router/providers`, `GET /api/router/health`, `POST /api/router/order`, `POST /api/router/providers/{id}/enabled`.

## [1.9.0] — 2026-06-26

### Added

- **Uninterrupted Mode (Phase 1) — automatic provider fallback.** New **Settings → Uninterrupted Mode** toggle. When on, if your selected model fails — offline / connection refused, rate-limited (429), overloaded (5xx), timed out, model-not-loaded, missing key, empty response, or a stream that breaks *before* any text — Chat Studio automatically retries the next provider in priority order across **local MLX + your configured cloud providers**, with no user action. The reply footer shows **via &lt;provider&gt;** and notes when it **fell back**.
  - Limits per the spec: 2 retries/provider, 5 attempts total, exponential backoff (1s/2s/4s), configurable request timeout (default 60s, time-to-first-token).
  - New modular `router.py` (`LLMRouter.generate`) — a standalone service so Story Studio / batch jobs can reuse the same fallback logic. Structured request logging to stderr.

> Coming in later phases: provider priority + per-provider enable/disable UI, health-status badges, a mid-stream **Continue with fallback** button (when a stream breaks *after* text), and the full test matrix.

## [1.8.0] — 2026-06-26

### Changed

- **Model picker is now tabbed — Local vs Cloud.** A one-click toggle switches between local MLX models and cloud models.
- Cloud models stay **grouped per provider** (the same model name on different providers is kept distinct).
- **Cloud providers without an API key are hidden by default** (shorter list); flip **show all** to reveal them, greyed-out and non-selectable, as a hint of what adding a key unlocks.

## [1.7.1] — 2026-06-26

### Changed

- The Chat model dropdown is now grouped with dividers: a **🖥 Local (MLX)** section and one **☁ <provider>** section per cloud provider, so local and cloud models are clearly separated.

## [1.7.0] — 2026-06-26

### Added

- **Live model fetch (ends model-id drift).** Each cloud provider now has a **Load all models (live)** button (Settings → Cloud providers) that pulls the provider's *current* `/models` catalog and adds it to the Chat dropdown — so you're never limited to (or stale against) the curated list. Public catalogs (HF Router, SambaNova) work with no key; key-required providers (GitHub, Groq, OpenRouter, …) fetch with your saved key. Loaded sets persist in the browser and can be cleared. New endpoint `GET /api/providers/{name}/models/live`.

> Live lists can include a provider's paid models — usage is billed by the provider. The curated paid-model gate still applies to the built-in shortlist.

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
