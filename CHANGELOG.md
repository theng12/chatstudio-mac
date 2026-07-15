# Changelog — Chat Studio KH

All notable changes to Chat Studio KH are documented here.

Versioning follows [Semantic Versioning](https://semver.org/) with this project-specific interpretation:

- **MAJOR** (1.x.x → 2.x.x) — breaking change. Re-install required.
- **MINOR** (1.1.x → 1.2.x) — new feature / new model family. Re-install to pick up new Python deps.
- **PATCH** (1.2.0 → 1.2.1) — bugfix / UI tweak / catalog entry within an existing family. **Just run Update** from the Pinokio sidebar.

---

## [1.22.0] — 2026-07-15

### Added — safe optional automatic updates

- Settings now offers Off, Notify only, and automatic-install modes with daily
  or weekly checks, a staggered 03:00 maintenance hour, and idle-only protection.
  The default remains Off and saving validates the LaunchAgent separately.
- Added installed/latest versions, last/next checks, live updater states, defer
  reasons, results, retry, Check now, Update now, Update after current work,
  release notes, and technical details.
- A short-lived launchd helper works without an open browser. Chat responses,
  streams, MLX model loading/generation, and downloads all block installation.

### Safety and recovery

- Every install requires the fixed origin, `main`, a clean fast-forward, enough
  disk space, dependency and import checks, healthy restart, and the expected
  version/build. Dirty, detached, divergent, rewritten, or unexpected repos are
  refused without changing files.
- Service and Pinokio Start modes are restarted independently, a per-app lock
  prevents update races, and one bounded rollback attempt restores matching
  requirements and verifies the previous healthy version after failure.
- Logs rotate under `logs/auto_update/`, secrets are redacted, duplicate agents
  cannot accumulate, and Reset unloads/removes the updater before the environment.

### Verified

- Added 19 focused safety tests and passed a real launchd enable/validate/disable
  cycle. Full tests, compilation, JavaScript/launcher parsing, dependency checks,
  isolated API health, and desktop/compact browser QA passed.

## [1.21.6] — 2026-07-15

### Production audit — catalog truth, VLM dispatch, auth, and chat UX

- Reconciled all 46 catalog entries against current Hugging Face repository metadata: exact decimal download totals, companion-file coverage, family labels, and Apple Silicon memory floors. No cached model files were deleted.
- Corrected multimodal dispatch for Llama 4 Scout, Mistral Small 3.1, Gemma 3/4, and Qwen3.5 so supported snapshots use `mlx-vlm`; cached config inspection remains a safety net for downloaded models.
- Removed query-string fleet-token authentication to prevent secrets leaking into logs, browser history, and referrers. Header and cookie authentication remain supported, with regression coverage.
- Added visible rename/delete success and failure feedback, preserved the reader's scroll position during streaming, and labelled verified model sizes and VLM entries in the Models tab.
- Added catalog integrity and vision-metadata regression tests. Cached local generation smoke tests completed for Llama 3.2 3B, Gemma 3 4B, and Gemma 4 E2B with sequential unloads/model switching. Vision image input for uncached multimodal entries was not downloaded or physically tested to avoid an unnecessary multi-GB download.
- No dependency changes were needed; the existing locked MLX/MLX-LM/MLX-VLM stack passed import and integrity checks. Existing FastAPI lifespan and TestClient deprecation warnings remain third-party/project modernization follow-ups.

## [1.21.5] — 2026-07-13

### Fixed — saved fleet credentials apply without restarting Chat Studio

- Protected requests now verify against the current owner-only fleet-token file instead of the value captured at process startup. Saving or rotating the credential in Studio Hub takes effect immediately for a running Chat Studio.
- Authenticated browser cookies are refreshed to the current credential after a successful request.

Verified with a live-rotation middleware regression test plus the full test suite. No launcher or dependency changes; **Just run Update**.

## [1.21.4] — 2026-07-09

### Added — orphaned download partials are now swept on startup (no re-download needed)

Follow-up to 1.21.3: that release de-duplicated `.incomplete` partials in the byte count and pruned them at the start of the *next* download — but a model that already finished downloading kept its orphan partial indefinitely (harmless, ~0.6 GB wasted) unless you happened to re-download it.

- **New `prune_all_incomplete()` runs once at server startup** (off-thread, can't delay boot): it sweeps every cached repo and deletes orphaned partials — any whose blob is already complete, and non-largest duplicates — while keeping the single furthest-along partial of a genuinely-incomplete blob so a resume still works. Reclaimed bytes are logged.

**What this means for an existing orphan:** the model itself was always fine to use (a leftover `.incomplete` is dead weight next to the completed file, not corruption). Now the leftover is removed automatically the next time the server starts — which an **Update** does — so no manual cleanup or re-download is needed.

Verified: sweep proven on a synthetic multi-repo cache with duplicate partials (reclaims the orphans, keeps the largest); service restarts clean.

### Notes

- PATCH bump (1.21.3 → 1.21.4) — startup cleanup only, no dependency changes. **Just run Update.**

## [1.21.3] — 2026-07-09

### Fixed — download progress could read past 100% ("3.0 GB / 2.3 GB"); catalog sizes corrected

Reported: downloading `Qwen3-4B-Instruct-2507-4bit` showed **3.0 GB / 2.3 GB, 100%** — the observed bytes exceeded the total.

**Root cause (the real bug): duplicate `.incomplete` partials were double-counted.** A retried/resumed download leaves more than one partial file for the *same* blob — huggingface_hub names them `<sha>.<etag>.incomplete` and writes a fresh `<etag>` temp on each attempt instead of resuming the old one. The on-disk cache had **two** partials of Qwen3-4B's single 2.26 GB weight file (2.0 GB + 0.9 GB), and `incomplete_bytes()` **summed** them → ~2.9 GB observed against a 2.3 GB total, plus ~0.6 GB of wasted disk.

- **`incomplete_bytes()` now de-duplicates by target blob** — groups partials by their SHA prefix and counts only the largest (furthest-along) one per blob, never the sum.
- **New `prune_stale_incomplete()` runs at the start of every download** — deletes orphaned partials (any whose blob is already complete, and all-but-the-largest for the same blob), reclaiming the wasted disk. huggingface_hub resumes from the survivor.
- **Observed bytes are now capped at the known total** as a final guard, so the bar can never read past 100% even on a transient edge case.

**Also — catalog sizes corrected against live Hugging Face metadata.** Surveyed all 46 models via the same `repo_info` call the downloader uses; updated 22 `size_gb` values to the real totals. The important ones were **under-reporters** that made the bar overshoot on their own: Ministral-3-8B (5.0→5.6), Devstral-Small-2-24B (14.0→15.1), Qwen2.5-14B/Coder-14B/DeepSeek-R1-14B (8.0→8.3), Qwen2.5-32B (18.0→18.4). Several others were rounded closer (Qwen3-4B 2.5→2.3, Llama-3.3-70B 42→39.7, Phi-4-mini 2.5→2.2).

Verified: dedup + prune proven on a synthetic two-partials-one-blob repo (counts 2000 not 2900; prunes the 900 orphan; cleans a completed blob's leftover partial); live `/api/catalog` now reports Qwen3-4B at 2.3 GB, Ministral-3-8B at 5.6 GB, Devstral at 15.1 GB.

### Notes

- PATCH bump (1.21.2 → 1.21.3) — download-accounting fix + catalog metadata, no dependency changes. **Just run Update.**

## [1.21.2] — 2026-07-13

### Fixed — force the classic HTTP downloader (the actual stall cause)

- Root cause of the "0 B/s forever" stall was **hf_xet**: its native downloader can wedge mid-file without honouring the read timeout, and it holds the blob lock while stuck — so even the retry added in 1.21.1 would have blocked on that lock. Chat Studio now **disables Xet for downloads** (`HF_HUB_DISABLE_XET`) and sets a firm 30s read timeout, so downloads take the classic HTTP path: a stalled read **raises**, releases the lock, and the retry loop resumes from the partial. Slightly slower than Xet, but it never hangs a fleet-wide push. Builds on the watchdog/retry/ETA fixes in 1.21.1.

## [1.21.1] — 2026-07-13

### Fixed — model downloads no longer hang forever + sane progress display

- **Auto-recover from stalled downloads.** `huggingface_hub`'s 10s read-timeout does not reliably fire for a Xet-backed download that wedges mid-file (bytes just stop with the socket still notionally alive), so a download could sit at **"0 B/s" forever**. The download manager now runs each attempt under a **progress watchdog**: if no new bytes land on disk for 75s it abandons that attempt and starts a fresh `snapshot_download`, which **resumes from the partial** (hf's `.locks/` coordinate). Bounded retries with backoff (up to 8) also recover transient connection/Xet errors — all without user action. Cancel stays responsive throughout.
- **No more absurd ETA.** The ETA used a decaying EMA speed with a `> 0` guard, but the EMA never reaches exactly 0 when bytes stop, so it divided a multi‑GB remainder by ~1e‑81 and showed **"ETA 1.6e+32h"**. ETA now requires a real speed floor (≥1 KB/s) and is hidden while stalled; a **"stalled — retrying (attempt N)"** indicator shows instead.
- Job status now includes `stalled`, `attempt`, and `retry_reason` for the UI. No new dependencies — **just Update**.

## [1.21.0] — 2026-07-12

### Added — secure fleet access and capability contract

- Remote API, OpenAI-compatible, session, and output access now requires the automatically shared StudioHub fleet token; loopback clients remain passwordless.
- Browser writes are same-origin protected, authenticated browser sessions use an HttpOnly cookie, and remote Studio pages prompt once per tab when a token is needed.
- Added normalized `GET /api/capabilities` metadata for chat, vision, and OpenAI-compatible operation preflight.

### Verification

- Python and JavaScript syntax checks pass. Security-contract tests cover public health/capability routes, protected catalog access, accepted fleet credentials, cross-origin write rejection, and private token permissions.

## [1.20.1] — 2026-07-12

### Security — safe Markdown, private local data, bounded vision input

- Markdown now escapes quotes before building links, preventing model-generated
  link targets from breaking out of `href` and injecting HTML attributes.
- Provider/Hugging Face credentials and server-side conversation history are now
  forced to owner-only (`0600`) permissions on read and after every atomic save.
- Vision chat accepts at most four uploaded images of 10 MB each. Remote image URLs
  are rejected to close the LAN-facing SSRF path, and malformed base64 now returns a
  useful validation error instead of silently disappearing.
- Chat, session, provider-key, and generation parameter payloads now have explicit
  length/range limits to prevent accidental or hostile memory/disk exhaustion.
- Remote update-version metadata is rendered as text instead of injected HTML.

### UX

- The attachment picker enforces the same four-image/10 MB limits before upload and
  explains rejected files in the existing toast, avoiding a delayed backend error.

### Verification

- Python, JavaScript, and HTML checks pass; Pydantic rejection cases, image decoding,
  Markdown attribute escaping, and owner-only file modes were exercised directly.
  `pip-audit` reports no known vulnerabilities in the installed environment.
- The documented LAN bind and permissive CORS remain unchanged pending fleet-wide API
  authentication, so existing OpenAI-compatible clients continue to work.

## [1.20.0] — 2026-07-10

### Added — vision-language chat (mlx-vlm) + the Qwen3.5 model family

Chat Studio can now run **vision-language models** — chat that understands attached images — alongside the existing text-only LLMs. Added the **Qwen3.5** family (mlx-community MLX builds), which is a unified VL family: every size is `image-text-to-text`, so it loads through **mlx-vlm** rather than mlx-lm.

**New engine path (`llm_engine.py`).** Model loading now detects vision models (catalog `is_vision` flag, or a `vision_config` / `*ForConditionalGeneration` architecture in the downloaded `config.json`) and routes them to `mlx_vlm.load` + `mlx_vlm.stream_generate`; text models keep loading through `mlx_lm` exactly as before. The change is **additive** — the text path is untouched, and if mlx-vlm isn't installed only the vision models are affected (they report "vision engine missing; run Update"), text chat keeps working.

**Image input.** `/api/chat/completions` accepts an optional `images` array (data URLs / base64) applied to the current turn. The chat composer shows a 📎 attach button (only for vision models), previews attachments, and renders them inline in the conversation. `mlx-vlm>=0.6.4` added to `requirements.txt` — it reuses the existing mlx / mlx-lm floors and requires transformers <5.13, which the current `>=5.12` floor already satisfies (5.12.x).

**Qwen3.5 catalog family (7 entries).** 0.8B / 2B / 4B / 9B (dense, `-MLX-4bit`) and 27B / 35B-A3B / 122B-A10B (larger + MoE, plain `-4bit`). Sizes and memory floors set from the real Hugging Face repo sizes (0.7 / 1.8 / 3.1 / 6.0 / 16.1 / 20.4 / 69.6 GB). The 9B is the recommended pick.

**⚠️ Requires a reinstall + testing.** Because it adds a dependency (mlx-vlm and its transitive deps: Pillow, opencv, mlx-audio, …), you must **Update then reinstall** so the env picks up mlx-vlm before vision models will load. This feature was authored against the mlx-vlm 0.6.4 API (verified `qwen3_5`/`qwen3_5_moe` support and the `load` / `apply_chat_template` / `stream_generate` signatures) but was **not** run end-to-end here — please confirm a vision model loads and answers an image question after reinstalling. Text chat is unaffected either way.

## [1.19.8] — 2026-07-10

### Fixed — download ETA settle-guard + dangerous model-size/memory under-counts

**Absurd download ETA (`downloads.py`).** Same suite-wide fix: the speed EMA's first near-zero sample (taken before real bytes land) produced ETAs like "99679m 03s" seconds after clicking Download. `eta_seconds` is now suppressed until the job has ≥3 s of runtime. (`formatDuration()` already had hour rollup, so the frontend was left unchanged.)

**Corrected 4 dangerous catalog under-counts.** Some entries listed a fraction of their real size with a too-low memory floor — most seriously `Llama-4-Scout-17B-16E` (a 16-expert MoE) was catalogued at 10 GB / 16 GB-floor but is really a 61 GB download that would hard-OOM a 16 GB Mac; it is now 61 GB / 64 GB. Also `Qwen3-Coder-30B-A3B` 9→17 GB (floor 16→24), `Nemotron-3-Nano-Omni-30B-A3B` 9→20 GB (floor 16→24), and `Ministral-3-3B` 2→2.8 GB. Verified against the HF API `blobs=true` listing.

**Removed prior-generation Gemma 2.** `gemma-2-2b-it-4bit` and `gemma-2-9b-it-4bit` are superseded at equal sizes by the Gemma 3 / Gemma 4 entries; both were removed along with the now-empty `gemma2` family definition.

**Checked, left unchanged:** the remaining LLM sizes/floors were audited against real HF sizes and are accurate (LLM runtime memory tracks model size, so those floors are sound). `py_compile` clean; catalog re-imports to 39 models.

## [1.19.7] — 2026-07-10

### Fixed — Version badge no longer uses an undefined color variable

The header badge referenced `--card`, which does not exist in Chat Studio's palette.
Browsers discarded the declaration and rendered the badge background transparent. It
now uses the established panel color, matching the intended header treatment.

### Verification

- Confirmed the live pre-fix computed background was transparent, then verified the
  corrected stylesheet resolves to the panel color with no JavaScript or layout errors.
- Provider navigation, API snippets, model formatting, and chat behavior were checked
  and deliberately left unchanged.

---

## [1.19.6] — 2026-07-10

### Changed — Conversation chrome is quieter and easier to scan

The chat workspace mixed emoji-heavy navigation, oversized rounding, a decorative
backdrop, and wide text controls around an otherwise dense tool. Primary tabs are now
clean text labels, the active view has a clearer accent, user messages use a restrained
warm tint to separate roles, and Send/Stop are stable square icon controls with accessible
labels. The existing provider-card settings navigation remains unchanged.

### Verification

- Validated JavaScript and HTML, exercised the live chat shell at desktop and mobile
  widths, and confirmed no horizontal overflow or page errors.
- Message streaming, session history, model loading, provider routing, and settings
  behavior were checked and deliberately left unchanged.

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
