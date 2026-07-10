# Changelog — Chat Studio KH

All notable changes to Chat Studio KH are documented here.

Versioning follows [Semantic Versioning](https://semver.org/) with this project-specific interpretation:

- **MAJOR** (1.x.x → 2.x.x) — breaking change. Re-install required.
- **MINOR** (1.1.x → 1.2.x) — new feature / new model family. Re-install to pick up new Python deps.
- **PATCH** (1.2.0 → 1.2.1) — bugfix / UI tweak / catalog entry within an existing family. **Just run Update** from the Pinokio sidebar.

---

## [1.19.5] — 2026-07-10

### Changed — Version now shown as a badge in the top-right header (consistent across all sibling apps)

The app version was displayed inconsistently across the Studio fleet (bottom footer on
some, top-right on Chat, missing on Video). It's now a small `v1.19.5`-style badge in the
top-right of the header on every app, matching Chat Studio — visible at a glance without
scrolling to a footer.

### Notes

- PATCH bump (1.19.4 → 1.19.5) — frontend only (`index.html` + `style.css`). Served with
  no-cache headers, so it appears on the next browser reload without a restart.

---
## [1.19.4] — 2026-07-10

### Fixed — Update reinstalls the service (rewrites the launchd plist) instead of kickstarting a stale one

The service scripts were renamed from generic `serve.sh` / `watchdog.sh` to
`<app>-serve.sh` / `<app>-watchdog.sh`, and the launchd plist's `ProgramArguments`
now points at the renamed script. A machine with the service already installed has
a plist pointing at the OLD `serve.sh` — so a plain **kickstart** (`restart_service.sh`)
would relaunch a plist pointing at a now-deleted path and the service would fail to
come back up after an update.

`update.js` (and `install_generation.js`) now restart the service with
**`install_service.sh`** instead of `restart_service.sh`. `install_service.sh`
regenerates the plist to match the current on-disk scripts *before* relaunching
(bootout → bootstrap → kickstart), so the rename is folded in automatically. It's
idempotent and safe to run on every update.

### Notes

- PATCH bump (1.19.3 → 1.19.4) — launcher scripts only. Applies only where the app
  runs as a launchd service (`service/.installed`); the `start.js` path is unchanged.

---
## [1.19.3] — 2026-07-10

### Added — In-app auto-check banner: tells you when to update instead of failing silently

On load the web UI checks `GET /api/update-status` and shows a dismissible banner when this install needs attention:

- **A newer version is published** — compares this install's VERSION against the repo's published VERSION (fetched from GitHub raw, cached ~6h, in a background thread so it never blocks). Banner: "⬆ Update available (vX → vY)", pointing at the one-click **Update** button in the Pinokio sidebar.

Detect-in-app, apply-via-sidebar: a sandboxed web page (external browser, Tailscale) can't reliably drive Pinokio's script runner, so the banner points at the sidebar's one-click Update rather than trying to self-update. The banner is self-contained (no framework coupling) and degrades silently if the endpoint isn't live yet (e.g. a running service that hasn't restarted onto the new build).

### Notes

- PATCH bump (1.19.2 → 1.19.3) — backend adds `GET /api/update-status`; frontend adds the banner to `index.html`. No change to existing features.

---
## [1.19.2] — 2026-07-10

### Fixed — One-click Update that works in service mode

Overhauled the update flow. The old "Update & Restart" was hardwired to stop/start `start.js`, but in production this app runs as an always-on launchd **service** — so it stopped nothing and then launched a *second* server that fought the service for the fixed port, leaving updates half-applied.

- **One Update button, correct in every run mode.** The unified `update.js` detects the mode and restarts the **real** server (kickstart the service **or** start `start.js` — never both), so updating no longer requires manually stopping production first.
- **Deps install from source** (`requirements.txt`) rather than a lock that can drift.
- **"Update & Restart" folded into "Update"** (kept as a back-compat alias that forwards to `update.js`).

### Notes

- PATCH bump (1.19.1 → 1.19.2) — launcher scripts only (`update.js`, `update_and_restart.js`, `pinokio.js`). No app-code change.

---
## [1.19.1] — 2026-07-09

### Fixed — cryptic "'str' object has no attribute '__module__'" MLX failure + recovery guidance

Reported on a second machine: the app showed **"MLX engine not available, mlx_lm not importable: 'str' object has no attribute '__module__'"** and no local models would load.

Root cause: `import mlx_lm` imports **transformers** at the top level, and that machine had drifted to a mlx-lm / transformers version combination different from the verified one (it was installed weeks ago with floor-based `>=` requirements, before the v1.19.0 lockfile existed, and its old `update.js` had no `git pull` step so it could never self-heal). The error is transformers failing during its own import against an incompatible sub-dependency — nothing to do with the model or the API.

- **`transformers` / `tokenizers` are now explicit floors in `requirements.txt`** (they were invisible transitive deps of mlx-lm before). They are the single most drift-prone part of the import chain, and the exact versions are already pinned in `requirements.lock.txt` — this just documents the sensitivity and stops a stale resolver from pulling an incompatible transformers.
- **The "MLX engine not available" banner now shows a recovery path** when the failure is an actual import error (not a not-yet-installed env): Update → Reset → Install, which rebuilds the environment from the committed lockfile.

**How to fix an already-drifted machine** (the reported case — a lockfile only helps installs that happen *after* it exists): Update the app to pull the latest lockfile, then run **Reset** (deletes `conda_env`) → **Install** (rebuilds from the pinned versions). Future fresh installs are already protected by the v1.19.0 lockfile.

Verified: floors satisfied by the live env; `requirements.lock.txt` already pins `transformers==5.12.1` / `tokenizers==0.22.2`; `index.html` parses clean and the live server serves the new banner.

### Notes

- PATCH bump (1.19.0 → 1.19.1) — docs + a frontend banner hint, no package versions changed. **Just run Update.**

## [1.19.0] — 2026-07-09

### Added — dependency lockfile: fresh installs are now reproducible forever

The failure mode this closes: `requirements.txt` uses version **floors** (`mlx-lm>=0.31`), so a fresh install months from now would resolve to whatever PyPI serves that day — one breaking release in any dependency bricks the app on a new machine while existing installs keep working, and the difference is invisible until it bites.

- **`app/requirements.lock.txt`** — the full 50-package pinned set of a known-good install (`pip freeze` of the verified env, with conda's local `file://` reference for `packaging` normalized to a real PyPI pin). Python itself was already pinned (`python=3.12` in install.js).
- **`install.js` and `update.js` now install from the lock**, not the floors file. A brand-new machine gets the byte-identical package set this app was last verified against.
- **Upgrades become deliberate:** edit floors in `requirements.txt` → install → verify the app works → regenerate the lock (flow documented in the lock's header) → commit. Every dependency change is now a reviewed, revertable git commit instead of silent drift.
- **`update.js` also gained a `git pull` step** (guarded by `.git` existing) — its header claimed "not cloned from a git remote," which stopped being true when this repo went up on GitHub; clones installed via Pinokio's Download-from-URL now get code + lock updates in one click.

Verified: `uv pip install -r requirements.lock.txt` against the live env → "Checked 50 packages in 81ms," all satisfied; both launcher scripts pass `node --check`.

### Notes

- MINOR bump (1.18.4 → 1.19.0) — install-pipeline change, no package versions changed (the lock pins exactly what's already installed). **Just run Update.**
- The lock is macOS-arm64/py3.12-specific, matching this app's declared `platform`/`arch` — not a limitation, just a note for anyone forking to another platform.

---

## [1.18.4] — 2026-07-08

### Improved — Provider API keys are easier to find and focus

The Cloud providers settings were still a long vertical list, so adding or testing a key meant hunting through every provider row. This was especially rough now that Chat Studio ships with 20 hosted providers.

- Added a compact provider card picker above the detailed key editors.
- Added provider/model search so the list can be filtered before editing.
- Clicking a provider card now scrolls its full editor row into view, highlights it, and focuses the API-key field.
- Kept the existing Save, Test, Get key, paid-model toggle, and live-model controls unchanged.

**Verified:** frontend syntax check, backend import compile, HTML parser smoke check, and live Settings smoke test against the running service at desktop and mobile widths. No launcher scripts were changed; `start.js` still uses the required `input.event[1]` URL capture/local.set pattern.

### Notes

- PATCH bump (1.18.3 → 1.18.4) — frontend-only Settings UX polish. **Just run Update** (or Update & Restart in service mode).

## [1.18.3] — 2026-07-08

### Fixed — Start now refuses to compete with startup service mode

The startup service already takes over port `47871` when installed, and the service-mode sidebar hides the normal Start button. But `start.js` itself still had no direct guard, so any stale menu, direct script launch, or automation path could still try to start a second Uvicorn server on the same fixed port and fail with "address already in use."

`start.js` now checks for `service/.installed` before launching the server. If service mode is active, it exits immediately with a clear message telling the user to use **Open UI (service)** or uninstall the startup service first. The existing Uvicorn URL capture and `local.set` behavior are unchanged.

**Verified:** `node --check start.js`, direct inspection against the required Pinokio URL-capture pattern (`input.event[1]`), and current logs showing service install already takes over the same port by stopping the previous Pinokio Start process.

### Notes

- PATCH bump (1.18.2 → 1.18.3) — launcher guard only, no app/backend change. **Just run Update**.

## [1.18.2] — 2026-07-08

### Fixed — Settings now has a clearer setup path and no hidden diagnostics crash

After pulling the latest Settings refresh, the page worked but every control had the same visual weight: fallback behavior, default model, chat defaults, provider keys, engine diagnostics, and server details all appeared as one long stack. That made the first-time setup path hard to scan, especially now that Chat Studio has 20 cloud providers.

- Added a compact Settings status header for fallback state, connected provider count, and MLX readiness.
- Grouped the page into **Chat Behavior**, **Access**, and **System** sections so related controls sit together.
- Reworked cloud provider rows with a connected/needs-key summary, clearer per-provider metadata, and consistent action rows for Save/Test/Get key/Load live models.
- Fixed a hidden Alpine expression in the Engine diagnostics block that could throw `Cannot read properties of null (reading 'stderr')` before dependency-repair output existed.

**Verified:** `node --check app/frontend/app.js`, `python3 -m py_compile` for backend settings/provider routes, HTML parser smoke check, live `curl` against the running service's no-cache static assets, and a headless Chrome pass on the live Settings tab at desktop and mobile widths. The live backend still reports `1.18.1.b8b7def` until the running service is restarted, but the static UI updates are served immediately.

### Checked and left unchanged

- No launcher scripts were changed. `start.js` already follows the required capture/local.set pattern, using `input.event[1]` from the Uvicorn URL capture.
- Provider save/test/live-model APIs were left untouched; this is a frontend organization and guard fix only.
- The existing inline sliders and controls were kept to avoid changing saved settings behavior.

### Notes

- PATCH bump (1.18.1 → 1.18.2) — frontend-only UI/UX polish plus one Alpine null guard. **Just run Update** (or Update & Restart in service mode).

## [1.18.1] — 2026-07-02

### Fixed — "502 (No body)" on cloud completions is now an informative error, and logged

Diagnosing continued Story Studio 502s on NVIDIA free models revealed two gaps rather than a broken route (small NVIDIA models answered in 1–2 s throughout):

- **`str(e)` is empty for httpx timeouts.** When NVIDIA's congested free tier queued a big model past our 120 s read timeout (measured: `llama-3.3-70b` took **49 s** to answer an 8-token prompt — sometimes it exceeds the window entirely), the 502's `detail` was `str(httpx.ReadTimeout)` — an empty string. That's the literal "502 (No body)" clients saw. Both cloud error paths (`/api` and `/v1`) now build the detail as `<provider> · <model id>: <ExceptionType>: <message>`, so a timeout reads like `NVIDIA NIM · meta/llama-3.3-70b-instruct: ReadTimeout:` instead of nothing.
- **`/v1` cloud failures were never logged server-side.** The `/api` streaming path printed tracebacks; the `/v1` path silently returned the 502. Both now print a `[chat studio] cloud error (v1|api): …` line to the service log, so the next "why did this 502" starts with an answer in `logs/service/server.err.log` instead of an empty access-log line.

Verified live: a request for a retired model now returns a 502 whose body names the provider, model, and NVIDIA's full 410 message — and the same line appears in the service log.

### Notes

- PATCH bump (1.18.0 → 1.18.1) — error-reporting only, no behavior change on success paths. **Just run Update** (or Update & Restart in service mode).
- Root cause of the ongoing 502s themselves is upstream: NVIDIA's free tier heavily queues large models (70B-class) at the moment. Small/mid models (8B, Gemma 4 31B) are fast. Clients that need reliability should pick a smaller NVIDIA model, another free provider, or turn on Uninterrupted Mode in the Chat UI.

---

## [1.18.0] — 2026-07-02

### Added — six more providers (20 total)

All endpoints probe-verified before wiring (each answered a real 401/400 at its documented path):

- **Mistral La Plateforme** — official API with a genuine rate-limited **free tier** (same model as Gemini AI Studio), so its curated models (Large, Medium, Small, Magistral, Codestral, Nemo) live in the **☁ Free tab**. Live-listed.
- **Together AI** — big open-model catalog (Llama, Qwen, DeepSeek, Mixtral). Live-listed, paid.
- **xAI (Grok)** — Grok 4.3 / 4 / 3-mini direct. Live-listed, paid.
- **Fireworks AI** — fast open-model serving (note their long `accounts/fireworks/models/…` id format). Live-listed, paid.
- **Moonshot (Kimi)** — Kimi K-series direct via the global endpoint. Live-listed, paid.
- **Perplexity** — search-grounded answers with live web citations; a genuinely different capability from other providers. Static list (no `/models` endpoint; also NB their API has no `/v1` prefix). Paid.

All existing machinery applies automatically: all-paid providers stay hidden until their paid toggle is on, live lists refresh on a 60s TTL with curated fallback, the error-in-200 guard covers streaming quirks, and models sort themselves into the ☁ Free / 💳 Paid tabs per model.

### Notes

- MINOR bump (1.17.1 → 1.18.0) — new providers, no new deps, no schema change. **Just run Update** (or Update & Restart in service mode).
- Curated ids are best-effort for the paid five (unverifiable without keys) — live listing corrects drift on the five that support it; Perplexity's `sonar*` family is stable.

---

## [1.17.1] — 2026-07-02

### Fixed — live-loaded models on an all-paid provider landed in the ☁ Free tab

The free/paid tab split has always been **per-model** (a mixed provider like OpenCode shows its 4 free models under ☁ Free and its 7 paid under 💳 Paid; same for OpenRouter's free tier vs paid flagships) — but "Load all models" hardcoded `free: true` on every live-fetched entry. On an all-paid provider (fal.ai, or official OpenAI/DeepSeek once live-listed), those models bill the user's account yet appeared under ☁ Free without a 💲 marker. No billing risk — the server's paid gate 403'd them regardless — but the tab was wrong and selecting one produced a confusing 403.

`GET /api/providers` now exposes `all_paid` per provider, and the picker marks live-fetched models on an all-paid provider as paid (💲, 💳 tab, behind the toggle). Verified live: `all_paid` correctly True for openai/anthropic/deepseek/fal/kie and False for opencode (its free tier keeps it mixed) and all free-tier providers.

### Notes

- PATCH bump (1.17.0 → 1.17.1) — one flag in `public_view()` + picker labeling, no schema change. **Just run Update** (or Update & Restart in service mode).

---

## [1.17.0] — 2026-07-02

### Added — two more paid providers: fal.ai and Kie.ai (14 total)

- **fal.ai** — their OpenRouter-powered, OpenAI-compatible LLM gateway (`fal.run/openrouter/router/openai/v1`). Bearer auth with a normal FAL key (probe-verified), bills through fal credits → gated as all-paid. **Live-listed** once a key is present; curated fallback covers GPT/Claude/Gemini/Llama/DeepSeek via fal.
- **Kie.ai** — unified chat API (`kieai.erweima.ai/api/v1`), Bearer auth, Kie-credit billing → all-paid. No `/models` endpoint (404 upstream), so static curated list (GPT-5.6, Claude Fable 5, Claude Opus 4.8, DeepSeek Chat — ids from kie.ai/market/chat; unverified without a key, may need a tweak on first real use).

### Fixed — errors wrapped in HTTP 200 no longer look like empty replies

Kie.ai (and gateways like it) return errors as **HTTP 200** with `{"code":401,"msg":…}` instead of a real error status — which our streaming reader treated as a successful stream containing zero tokens, i.e. a silent empty reply. `stream_chat()` now buffers a non-SSE trailing body and, when the stream produced nothing: a JSON error envelope raises a proper error (verified live: fake Kie key → `502 "Kie.ai error: Unauthorized…"`), and a plain non-streamed completion (a 200 with `choices` despite `stream:true`) is yielded as the reply instead of being dropped. Applies to every provider, not just Kie.

### Notes

- MINOR bump (1.16.0 → 1.17.0) — new providers, no new deps, no schema change. **Just run Update** (or Update & Restart in service mode).
- Verified: 14 providers registered; fal/kie hidden from `/v1/models` while keyless/untoggled; keyless chat routing returns clean 401; error-in-200 guard end-to-end with a deliberate bad key.

---

## [1.16.0] — 2026-07-02

### Added — Paid cloud providers + a three-way model picker (Local · Free · Paid)

The model catalog now has three explicit categories: **Local (MLX)**, **Free Cloud API**, and **Paid Cloud API**.

- **Four new paid providers**, pluggable the same way as the existing ones (Settings → Cloud providers → paste key → flip "Enable paid models"):
  - **OpenAI (official)** — `api.openai.com`, live-listed, curated fallback (GPT-5.5/5.4/5.3-codex/4.1)
  - **Anthropic (official)** — via their OpenAI-compat layer; curated list (Fable 5, Opus 4.8, Sonnet 5, Haiku 4.5). Static — their `/models` uses native auth, not Bearer.
  - **DeepSeek (official)** — `api.deepseek.com`, live-listed (deepseek-chat, deepseek-reasoner)
  - **OpenCode Zen** — coding-focused gateway (opencode.ai). Mixed catalog: **4 free models usable without the paid toggle** (Big Pickle, Nemotron-3 Ultra free, DeepSeek V4 Flash free, MiMo v2.5 free) plus 7 paid ones billed against OpenCode credit. Static list — their `/models` is metadata-shaped, not OpenAI-shaped.
- **Money-safety guards for all-paid providers:** a provider whose models are all paid (OpenAI/Anthropic/DeepSeek) is hidden from `/v1/models` and the picker entirely — even with a key saved — until its paid toggle is on. A key alone isn't consent to spend. Unknown model ids on an all-paid provider are also treated as paid (`parse_repo`), so a hand-typed novel id can't slip past the 403 gate.
- **OpenRouter's paid flagships now surface in `/v1/models`** when its paid toggle is on (previously curated-only in the UI): the free-only live list gets the allowed curated paid models appended. Toggling takes effect on the very next call — paid filtering happens per-request, outside the 60s live cache.
- **Chat picker is now three tabs** — 🖥 Local · ☁ Free · 💳 Paid. The Paid tab shows each provider's 💲 models, with the group disabled (and labeled why) until both the key is set and paid is enabled.

### Changed — every free provider is live-listed now

Groq, Cerebras, Gemini, HF Router, SambaNova, and GitHub Models joined OpenRouter and NVIDIA on the 60s-TTL live listing — `/v1/models` reflects each provider's actual current catalog, so a retired model can no longer be advertised and 502 on use (the v1.15.3 bug class, now closed for **all** providers). Curated lists remain as offline/error fallbacks. Verified live: Gemini went 4 curated → 36 live models (with their `models/` id prefix normalized away and the paid-curated `gemini-2.5-pro` correctly excluded while paid is off), HF Router 5 → 121.

### Notes

- MINOR bump (1.15.3 → 1.16.0) — new feature + new providers, no new Python deps, no schema change. **Just run Update** (or Update & Restart in service mode).
- Not live-verified: actual paid completions on the four new providers (no keys configured on this machine yet) — the routing/gating machinery is identical to OpenRouter's, which is verified. Paste a key, enable paid, and the models appear in the 💳 tab and `/v1/models`.

---

## [1.15.3] — 2026-07-02

### Fixed — NVIDIA is now live-listed too, closing the stale-id 502 window for good

Root cause of the Story Studio 502 report, from the service logs: `/v1/chat/completions` calls using `google/gemma-3-27b-it` got **HTTP 410 Gone** from NVIDIA (*"reached its end of life on 2026-05-12"*) and `qwen/qwen2.5-coder-32b-instruct` got **HTTP 404** (*"Function … not found"* — NVIDIA's phrasing for a delisted model), both relayed to the client as 502. v1.15.2 already dropped those two stale ids from the curated list, but the failure mode remained open: any future NVIDIA retirement would silently re-create it, because `/v1/models` advertised a hand-maintained snapshot.

- **NVIDIA now has `supports_live_listing=True`** — the same 60s-TTL live-listing mechanism OpenRouter uses — so `/v1/models` serves NVIDIA's actual current catalog and can no longer advertise a model their API stopped hosting. The expanded 32-model curated list from v1.15.2 stays as the offline/error fallback (and remains what the Settings UI shows before "Load all models"). This supersedes v1.15.2's "NVIDIA is served as a static list" note.
- NVIDIA's live catalog is ~100 models with no paid tier (all free with an API key), so `live_free_only` doesn't apply; the tightened non-chat filter from v1.15.2 keeps the live list chat-relevant.

**Verified:** completion against `provider:nvidia:google/gemma-4-31b-it` returns HTTP 200 with a real reply; both dead ids absent from `/v1/models`.

### Notes

- PATCH bump (1.15.2 → 1.15.3) — backend config only, no new deps, no schema change. **Just run Update** (or Update & Restart in service mode).

---

## [1.15.2] — 2026-07-01

### Changed — cloud model surfacing (NVIDIA + OpenRouter)

- **NVIDIA curated list expanded 7 → 32** verified chat/coding/reasoning models (Llama 3.x/4, Nemotron incl. Ultra 253B & 340B, DeepSeek V4, Qwen3, Mistral Large 3, Gemma 4, Phi, GPT-OSS, Granite, Yi, Jamba, DBRX, Codestral, StarCoder2, Kimi). NVIDIA is served as a **static** list (not live-listed), so this is what API consumers like **Story Studio** see — now 32 instead of 7. Also **dropped 2 stale ids** (`google/gemma-3-27b-it`, `qwen/qwen2.5-coder-32b-instruct`) that NVIDIA no longer hosts. The full 100+ catalog is still one click away via **Load all models** in the UI.
- **OpenRouter live listing is now free-only.** Its live catalog is 300+ (mostly paid), which flooded the picker and `/v1/models`; now filtered to the ~21 `:free` models via a new `live_free_only` provider flag. Paid OpenRouter flagships remain available through the curated list behind the paid toggle.
- **Tightened the non-chat filter** (added embeddings/reward/safety/retrieval/translate/parse/vision markers) so live lists stay chat-relevant.

## [1.15.1] — 2026-07-01

### Fixed — Numeric-formatting and terminology audit (same bug class as Voice Studio KH v1.7.2/v1.7.3)

First run of the sibling-app consistency-audit skill against Chat Studio. Checked every byte/size display and every state-label for the two bug classes found earlier in Voice Studio: GB-vs-GiB unit mismatches and terminology drift for the same underlying state.

**`formatBytes()` used binary (÷1024) math while labeling units decimally (`KB`/`MB`/`GB`/`TB`)** — the exact bug class Voice Studio fixed in v1.7.2/v1.7.3, independently reintroduced here. `formatBytes()` is the single shared renderer for live download progress (bytes observed/total, transfer speed) across both the Models-tab per-card download caption and the Downloads-tab job table — one fix covers every model. Root cause: the catalog's static `size_gb` (`catalog.py`, "~0.5-0.7 GB per billion params," decimal) and the live download total (real bytes from Hugging Face, run through `formatBytes`) were computed on different bases, so a model listed as "4.3 GB" would only ever show "~4.0 GB" downloaded — looking like the download fell short or stalled, when actually all the bytes arrived. `formatBytes()` now divides by 1000, matching the catalog's own decimal convention and Hugging Face's own byte reporting. Kept the function's existing rounding style (0 decimals for bytes, 1 decimal otherwise) — only the divisor was wrong.

**Terminology drift: "✓ cached" vs "✓ downloaded" for the identical state, same card.** The Models-tab card's title chip reads `✓ cached` when `m.cache.state === 'cached'`; a few lines down, the same card's action area read `✓ downloaded` for that exact same condition — both visible at once. "Cached" is this app's dominant term for the state (also used identically in the RAM-planner's model-picker chip) — standardized the action-area label to `✓ cached` to match.

**Checked and confirmed correct, deliberately left unchanged:**
- Every hardcoded state color (`.dot.ok/.bad`, `.chip.ok/.warn`, `.chip.fit-ok/-tight/-over`, `.test-result.ok/.err`, `button.link.danger`) resolves to the exact same RGB as `var(--ok)`/`var(--warn)`/`var(--bad)` — no duplicate/disagreeing palette, unlike Voice Studio's three-different-greens bug. `.banner.warn` and `.continue-banner` share one hardcoded darker amber pairing (`#221c10`/`#5a4a1f`) used consistently in both places for a deliberately more opaque "banner" treatment distinct from the translucent chip tint — the two instances agree with each other, so not a real bug.
- `size_gb_approximate: true` is set unconditionally for every catalog entry in `serialize_model()` (not per-entry) — the "approx. download" label already renders consistently for all 34+ models, so the catalog's disclosed estimate-vs-actual gap (a few percent, expected) is correctly and uniformly flagged to the user. No fix needed.
- Download interaction parity: Chat Studio has exactly one download entry point (Models-tab card → `startDownload()`, no confirmation dialog) and no second UI path to diverge from it — `/api/hub/search` exists server-side but has no frontend consumer, so there's no Hub-search download flow to compare against. `deleteSession()` (chat-history sidebar) is called identically from both its pinned and unpinned row markup. No custom modals exist anywhere in the app — `deleteSession`/`renameSession` use native browser `confirm()`/`prompt()`, which can't diverge in button order or styling. Nothing to fix.

### Notes

- PATCH bump (1.15.0 → 1.15.1) — frontend-only (`app.js`, `index.html`), no backend/schema change. Already live on the running server (static assets served fresh per request, cache-busted by the `?v=` query string) — confirmed via direct `curl` against `/assets/app.js` and `/` on the user's own running instance (port 47871) rather than restarting it. `node --check app.js` passed.

---

## [1.15.0] — 2026-06-26

### Added

- **Unload model** button in the Chat header — one click frees the loaded local MLX model from unified memory. A small **● &lt;model&gt; loaded** pill shows when a local model is resident.
- **Auto-unload on idle.** A loaded local model is freed automatically after **10 minutes unused** (e.g. once you've switched to a cloud model), with a **toast notice** when it happens. It transparently reloads on your next local message. New `POST /api/chat/unload`; `/api/health` now reports `loaded_model` / `idle_seconds` / `auto_unload`.

## [1.14.0] — 2026-06-26

### Added

- **Chat history.** Conversations now persist **server-side** (gitignored `sessions.json`, so history survives browser-cache clears and is visible from any device pointed at the server). A collapsible **history sidebar** in the Chat tab lets you:
  - **Search** across chat titles *and* message content,
  - **Pin** important sessions (pinned float to the top), **rename**, and **delete**,
  - **Open** a past session to **restore its full conversation** — continuing it re-sends that context to the model.
  - Sessions **auto-save** after each exchange; titles auto-derive from your first message. Toggle the sidebar with ☰.

## [1.13.1] — 2026-06-26

### Fixed

- **A fully-downloaded model could stay hidden** (reported "partial" and missing from the dropdown) when Hugging Face left behind a leftover `.incomplete` file — a duplicate of an already-completed blob from an interrupted retry. `cache_state` now ignores an `.incomplete` whose target blob is already complete, so the model shows and loads normally. (Hit with `gemma-3-4b-it-qat-4bit`; its upstream `index.json` is also mislabeled to phantom shards, but mlx-lm loads `model.safetensors` directly so that doesn't affect loading.)

## [1.13.0] — 2026-06-26

### Added

- **Uninterrupted Mode (Phase 4) — test suite.** `app/backend/router_tests.py`: a self-contained, network-free test matrix for the fallback router (11 scenarios — first-try success, offline→next, rate-limit/timeout retries-then-fallback, all-fail, empty response, break-before-text fallback, break-after-text interruption, disabled-skipped, missing-key-skipped, global attempt cap). Run from `app/`: `../conda_env/bin/python -m backend.router_tests`.

## [1.12.0] — 2026-06-26

### Added

- **Uninterrupted Mode (Phase 3) — Continue with fallback.** If a reply streams some text and *then* the provider drops (so the router can't silently swap mid-answer), the partial answer is kept and a **Continue with fallback →** button appears. Clicking it resumes on the next available provider — excluding the one that just broke — and appends to the same message. New `exclude_providers` field on the chat request.

## [1.11.0] — 2026-06-26

### Added

- **Uninterrupted Mode (Phase 2) — fallback order & health.** Settings now has a **Fallback order & health** panel: reorder providers with ↑/↓ (top = tried first), enable/disable each, and see a live **health badge** per provider — *online · slow · offline · rate-limited · no key*. Health is checked on launch and every 5 minutes. Local MLX + all cloud providers participate. New endpoints: `GET /api/router/providers`, `GET /api/router/health`, `POST /api/router/order`, `POST /api/router/providers/{id}/enabled`.

## [1.10.0] — 2026-06-26

### Added — RAM planner: interactive memory slider + live "Best for your RAM" picks (Models tab)

The Models tab's "Your Mac" banner became an interactive **hardware planner** so you can size models to a machine you don't own yet.

- **RAM slider + numeric entry + tier presets** (8 / 16 / 24 / 32 / 48 / 64 / 128 / 256 / 512 GB). Defaults to your detected RAM; drag/type to *preview* a different Mac (e.g. plan an M3 Ultra 512 GB before buying it). A `↩ My Mac` button snaps back to detected. The chosen budget persists across reloads.
- **Live hardware fit** — per-card fit chips and the existing **RAM fit** segmented filter (All / OK / Tight / Over) are now scored **client-side** against the slider via `fitFor()`/`effectiveRam`, so they re-score instantly with no `/api/catalog` round-trip. This also fixes the "Over" filter, which previously compared against a fit state the backend never emitted.
- **✨ Best for your RAM** — surfaces the highest-quality model in each lane (overall / code / reasoning / starter) that still fits the budget. At 8 GB it favours the small models; at 64 GB+ it upgrades to 70B-class.

**Frontend-only — no new Python dependencies. A plain _Update_ from the Pinokio sidebar is enough.**

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
