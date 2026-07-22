# Chat Studio (Mac)

Apple Silicon local LLM chat studio, built on [MLX](https://github.com/ml-explore/mlx). Sibling app to **ImageStudio Mac** (FLUX image generation), **VoiceStudio Mac** (text-to-speech), and **MusicStudio Mac**. Same scaffolding, focused on chat.

Chat Studio replaces juggling LM Studio as a second always-on app: it runs as a background service alongside the rest of the Studio family, with the same install/start/update/reset conventions and an OpenAI-compatible API so existing tooling (Continue.dev, Open WebUI, etc.) can point at it as a drop-in.

## What it does

- **Catalog of 46 verified MLX-ready instruction-tuned chat models** across 14 families, all pre-quantized by the `mlx-community` Hugging Face org — no conversion step needed. The catalog spans everyday assistants, fast/low-memory models, coding and reasoning, multilingual/Khmer-capable Qwen models, creative writing, long-context work, and vision/document-capable families.

  > Vision entries are dispatched through `mlx-vlm` and are labelled in the Models tab. The Gemma 3 1B entry is text-only; Gemma 3 4B/12B/27B, Gemma 4, Qwen3.5, Mistral Small 3.1, and Llama 4 Scout expose vision only when the installed processor supports the downloaded snapshot. Sizes are verified decimal totals for the current Hugging Face repository snapshots, including tokenizer, processor, config, and weight shards.
- **Chat tab** — pick a downloaded model from the dropdown (it loads on selection; only one model is kept in unified memory at a time) and chat. Responses **stream token-by-token** with Markdown/code rendering, a **Stop** button, and an inline **Params** popover (temperature, max tokens, top-p). A per-model **fit chip** flags whether a model comfortably fits your Mac's unified memory.
- **Settings tab** — a system prompt and generation defaults (saved in your browser), Hugging Face token with a **Test** button, an MLX engine-diagnostics panel, and server/connectivity info.
- **API tab** — your OpenAI-compatible base URL with one-click copy, the LAN/Tailscale URLs to reach it from other devices, and ready-to-paste **cURL / Python / JavaScript** snippets pre-filled with your loaded model.
- **OpenAI-compatible API** at `/v1` — `GET /v1/models`, `POST /v1/chat/completions` (streaming + non-streaming) — point existing OpenAI-client tooling at `http://localhost:47871/v1` (any non-empty API key works).
- **Smart downloads** with resume-on-retry — partial downloads pick up where they left off.
- **Direct API** — bound on `0.0.0.0:47871`, hit it from your main Mac over LAN, Tailscale, or anywhere on the network.
- **Runs as a background service** — install once, the API is always up, starts on boot, and self-heals if it crashes or hangs.

## How to use

1. Install: click **Install** in the Pinokio sidebar (creates the conda env + installs `mlx` / `mlx-lm`).
2. Start: click **Start** (runs uvicorn on port 47871 across all interfaces).
3. Click **Open UI** → **Models** tab → download a model. **Llama 3.2 3B Instruct (4-bit)** is the recommended starter — small and fast.
4. Switch to **Chat**, click **load** next to the model, and start chatting.
5. (Optional) Click **Install as Startup Service** in the sidebar to run Chat Studio as an always-on background service instead of manually starting it each time — see "Run as an always-on server" below.

Generation dependencies can be repaired without stopping Chat Studio first. Use **Install Generation** on a fresh environment or **Reinstall Generation** afterward; the launcher installs and verifies the pinned MLX stack, then restarts the active regular or service-mode server automatically.

The header's **What's New** button always shows the installed release version and the matching details from `CHANGELOG.md`.

## Automatic updates (optional)

Open **Settings → Automatic updates** and choose Off (the default), Notify only,
or Download and install automatically. Checks can run daily or weekly at the
selected maintenance hour; Chat Studio defaults to the family’s staggered 03:00
slot. Saving reports success only after the LaunchAgent is actually validated.

Keep **Update only while idle** enabled. Active local or cloud conversations,
response streams, queued/model-loading MLX work, and model downloads defer the
install without cancelling user work. **Update after current work** creates a
one-time retry even when the regular mode is Off.

The helper accepts only the expected GitHub origin and `main`, requires a clean
fast-forward and free disk space, installs dependencies, verifies imports, and
confirms both health and the running version/build. It never discards local
changes. Failure makes one bounded rollback attempt and reports the outcome.
Rotated technical logs are under `logs/auto_update/`; switching Off unloads and
removes the schedule immediately. Fix any named Git/service issue and use Retry
if the panel enters a Repair/failed state.

## Model memory management

Chat Studio keeps the current local LLM loaded by default so the next response
starts quickly. In Settings, **Balanced** releases it after 10 idle minutes,
**Memory Saver** after 2 minutes, and **Immediate** after each completed local
response. **Performance** is the default and never unloads automatically.

The Chat toolbar and Settings both provide **Release Memory / Unload Model**.
Automatic and manual cleanup wait for active model loading and generation to
finish, then remove the loaded model and clear available MLX/Metal allocator
caches. Downloaded weights and conversations remain on disk.

```text
GET  /api/memory-policy
PUT  /api/memory-policy   # { "mode": "performance|balanced|memory_saver|immediate" }
POST /api/memory/release
```

After Update and the next normal restart, Activity Monitor labels the backend
**Chat Studio Mac** instead of a generic Python process. Python remains the
runtime underneath the friendly title.

## Local storage policy

Chat Studio participates in Studio Hub's shared three-day / 80 GB fleet policy,
but it has no disposable generated media. The Settings card and standard API
therefore report zero eligible assets. Model weights and server-side chat
history are explicitly protected and Clean now never deletes them.

```text
GET  /api/storage-policy
PUT  /api/storage-policy          # { enabled, retention_days, max_gb }
POST /api/storage-policy/cleanup  # reports zero eligible assets
```

## Versioning

Current version is stored at the project root in [`VERSION`](VERSION).

### Release rule

Every shipped behavior, API, provider, model-catalog, dependency, launcher,
integration, or user-visible change must increment the numeric `VERSION` under
the semantic-versioning policy and add a matching top entry to
[`CHANGELOG.md`](CHANGELOG.md). The entry must clearly describe what changed,
what users should know, and relevant verification or limitations. This is the
single source for the in-app **What's New** panel; do not create a separate
frontend release-notes list.

The WebUI footer shows the running version. The same value is also surfaced at:

- `GET /api/version` → the current `VERSION` value and title
- `GET /api/health` → includes `app_version` and read-only `restart_rate`
- `GET /api/chat/diagnostics` → includes `app_version`
- `GET /api/auto-update/status` → updater settings and redacted state
- `GET /api/auto-update/readiness` → idle state and active-work reasons
- `POST /api/auto-update/settings` → save and validate the opt-in schedule
- `POST /api/auto-update/check` → safe version check
- `POST /api/auto-update/update` → update now or `{"after_current":true}`
- `POST /api/auto-update/retry` → retry a failed update

## API

Once running, the API is at `http://<your-mac-ip>:47871`. Both a native API and an OpenAI-compatible `/v1` alias are available.

### Native API

#### JavaScript

```js
// List the catalog
const r = await fetch("http://localhost:47871/api/catalog");
const { models, families } = await r.json();

// Load a model into memory (unloads any previously loaded model)
await fetch("http://localhost:47871/api/chat/load", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ repo: "mlx-community/Llama-3.2-3B-Instruct-4bit" }),
});

// Chat — streamed plain-text response
const res = await fetch("http://localhost:47871/api/chat/completions", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    repo: "mlx-community/Llama-3.2-3B-Instruct-4bit",
    messages: [{ role: "user", content: "Say hello in one sentence." }],
    stream: true,
  }),
});
const reader = res.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  console.log(decoder.decode(value));
}
```

#### Python

```python
import requests

# List catalog
r = requests.get("http://localhost:47871/api/catalog").json()
for m in r["models"]:
    print(m["repo"], m["size_gb"], "GB", m["cache"]["state"])

# Load a model
requests.post(
    "http://localhost:47871/api/chat/load",
    json={"repo": "mlx-community/Llama-3.2-3B-Instruct-4bit"},
)

# Chat (non-streaming)
r = requests.post(
    "http://localhost:47871/api/chat/completions",
    json={
        "repo": "mlx-community/Llama-3.2-3B-Instruct-4bit",
        "messages": [{"role": "user", "content": "Say hello in one sentence."}],
        "stream": False,
    },
)
print(r.json()["content"])
```

#### curl

```bash
# Catalog
curl http://localhost:47871/api/catalog | jq .

# Load a model
curl -X POST http://localhost:47871/api/chat/load \
  -H "content-type: application/json" \
  -d '{"repo":"mlx-community/Llama-3.2-3B-Instruct-4bit"}'

# Chat (streaming, plain text chunks)
curl -N -X POST http://localhost:47871/api/chat/completions \
  -H "content-type: application/json" \
  -d '{"repo":"mlx-community/Llama-3.2-3B-Instruct-4bit","messages":[{"role":"user","content":"Say hello in one sentence."}],"stream":true}'
```

### OpenAI-compatible API (`/v1`)

Point local OpenAI-client tools at `http://localhost:47871/v1` as the base URL. Loopback requests are open for local use. Remote requests require the configured `X-Studio-Token` header (or `Authorization: Bearer …`); never put a token in a URL query string.

```bash
# List models (only models currently cached on disk are listed)
curl http://localhost:47871/v1/models | jq .

# Chat completion — standard OpenAI schema
curl -X POST http://localhost:47871/v1/chat/completions \
  -H "content-type: application/json" \
  -d '{
        "model": "mlx-community/Llama-3.2-3B-Instruct-4bit",
        "messages": [{"role": "user", "content": "Say hello in one sentence."}],
        "stream": false
      }'
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:47871/v1", api_key="not-needed")
resp = client.chat.completions.create(
    model="mlx-community/Llama-3.2-3B-Instruct-4bit",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(resp.choices[0].message.content)
```

## Folder layout

```
chatstudio-mac/
├── app/
│   ├── backend/        # FastAPI server (Python)
│   │   ├── main.py         # routes, CORS, static frontend mount
│   │   ├── catalog.py      # MLX chat-model catalog (families + models)
│   │   ├── llm_engine.py   # load/unload + streaming generation via mlx_lm
│   │   ├── downloads.py    # HF snapshot_download job manager + SSE
│   │   ├── cache.py        # HF cache state inspection
│   │   ├── settings.py     # persisted HF token
│   │   └── system_info.py  # Apple Silicon chip + RAM detection
│   ├── frontend/       # Single-page UI (Alpine.js, no build step)
│   └── requirements.txt
├── install.js          # Sets up conda env + deps (mlx, mlx-lm, fastapi, ...)
├── start.js            # Launches uvicorn on port 47871
├── update.js           # Reinstalls deps + restarts the service if installed
├── reset.js            # Nuke the conda env
├── pinokio.js          # Sidebar menu
├── pinokio.json        # Pinokio metadata
├── service.js / service_status.js / service_restart.js / unservice.js
├── install_service.sh / uninstall_service.sh / serve.sh / watchdog.sh /
│   status_service.sh / restart_service.sh   # launchd background-service plumbing
└── VERSION
```

## Ports

Chat Studio uses **port 47871** so it doesn't clash with ImageStudio (47868), MusicStudio (47869), or VoiceStudio (47870). All four can run simultaneously.

## Run as an always-on server (auto-start + self-healing)

By default you start the app by opening Pinokio and clicking **Start**. If instead you want this Mac to behave like a **server** — the API always up, started automatically on boot, and self-healing — use the one-click service.

### Turn it on
In the Pinokio sidebar click **❤️ Install as Startup Service**. That's it. It:

- Installs a macOS **launchd LaunchAgent** that runs the server (`serve.sh`) on **port 47871**.
- **Starts automatically** every time you log in (so it comes back after a reboot).
- **Restarts itself if it crashes** (launchd `KeepAlive`).
- Adds a **health watchdog** that pings `/api/health` every 60s and relaunches
  the server only after three consecutive misses. Any successful response clears
  the streak immediately, so a single slow probe cannot restart healthy work.

The same health response exposes a bounded `restart_rate` snapshot for Studio
Hub: restart counts over one hour, 24 hours, and seven days; the latest restart;
and `healthy`, `warning`, or `critical` status. Warning starts at 3/hour,
4/day, or 10/week; critical starts at 6/hour, 12/day, or 30/week. This signal is
observability only—it never triggers a restart or changes chat dispatch.

No admin/sudo needed for this step — it's a per-user agent. To remove it later, click **Uninstall Startup Service**.

Logs live in `logs/service/`. Reach the API over Tailscale/LAN at `http://<this-mac>:47871`, and the OpenAI-compatible endpoint at `http://<this-mac>:47871/v1`.

> Use the **service OR** Pinokio's **Start** button — not both. They share port 47871, so running both makes them fight over it.

### One-time Mac settings for full power-cut recovery (why they matter)
The service handles *software* restarts. To survive an actual **power outage** with zero human steps, each Mac also needs three system settings (admin-level, done once — the button does **not** change these):

1. **Power back on automatically when electricity returns**
   ```bash
   sudo pmset -a autorestart 1
   ```
   *Why:* otherwise the Mac just stays off after the power drops and comes back. This tells it to boot itself the moment power is restored.

2. **Enable Automatic login** — System Settings ▸ Users & Groups ▸ *Automatically log in as …*
   *Why:* the Apple GPU (Metal / MLX) is **only available inside a logged-in session**. A service that starts before login can't use the GPU, so models would fail to load or fall back to slow CPU. Auto-login gets the Mac into a real session by itself.

3. **Turn FileVault OFF** — System Settings ▸ Privacy & Security ▸ FileVault
   *Why:* with FileVault on, a reboot stops at the encrypted-disk password screen and **never reaches auto-login** — so the server never comes back on its own. (On a Tailscale-only box this is a reasonable trade. If you must keep FileVault, you'll have to type the disk password in person after every power cut.)

With all three set **plus** the startup service installed: power returns → Mac powers on → auto-logs in → the server (and watchdog) start with GPU access → and any crash/hang is auto-recovered. Fully hands-off.

### Rolling it out to many Macs
The service files ship inside this launcher, so on each Mac you just click **Install as Startup Service** once. Do the three system settings once per machine (or bake them into your provisioning). After that, updates flow through the normal **Update** button.

## Sizing note

Catalog `size_gb` values are **verified decimal repository totals** from the release audit's Hugging Face file metadata snapshot. They include weights and companion files; the live `/api/cache` and `/api/downloads` endpoints report actual on-disk bytes after download.

## License

The launcher scripts in this repo are MIT. Each chat model has its own upstream license (Llama Community License, Apache-2.0 for Qwen/Mistral/DeepSeek-distill, Gemma's terms, MIT for Phi) — check the model card on Hugging Face before commercial use.
