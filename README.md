# Chat Studio (Mac)

Apple Silicon local LLM chat studio, built on [MLX](https://github.com/ml-explore/mlx). Sibling app to **ImageStudio Mac** (FLUX image generation), **VoiceStudio Mac** (text-to-speech), and **MusicStudio Mac**. Same scaffolding, focused on chat.

Chat Studio replaces juggling LM Studio as a second always-on app: it runs as a background service alongside the rest of the Studio family, with the same install/start/update/reset conventions and an OpenAI-compatible API so existing tooling (Continue.dev, Open WebUI, etc.) can point at it as a drop-in.

## What it does

- **Catalog of 19 MLX-ready instruction-tuned chat models** across 8 families, all pre-quantized by the `mlx-community` Hugging Face org — no conversion step needed:
  - **Llama** (3.2 3B — recommended starter, 3.1 8B)
  - **Qwen** (2.5 7B, 2.5 14B, 2.5 Coder 7B)
  - **Gemma 4** (E2B, E4B, 12B, 26B-A4B MoE, 31B — Google's April 2026 release, QAT 4-bit)
  - **Gemma 3** (1B, 4B, 12B, 27B — QAT 4-bit)
  - **Gemma 2** (2B, 9B Instruct)
  - **Mistral** (7B Instruct v0.3)
  - **Phi** (3.5 Mini Instruct)
  - **DeepSeek** (R1 Distill Qwen 7B — reasoning)

  > Gemma 3 and Gemma 4 are multimodal upstream; Chat Studio runs them as **text-only** chat (image/audio input isn't exposed in this UI). The Gemma entries use Google's **QAT** (quantization-aware-trained) 4-bit builds for near-full-precision quality, and their listed sizes are **real on-disk totals** from Hugging Face, not estimates.
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

## Versioning

Current version is stored at the project root in [`VERSION`](VERSION).

The WebUI footer shows the running version. The same value is also surfaced at:

- `GET /api/version` → `{"app_version": "1.0.0", "title": "Chat Studio KH"}`
- `GET /api/health` → includes `app_version`
- `GET /api/chat/diagnostics` → includes `app_version`

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

Point any OpenAI-client tool (Continue.dev, Open WebUI, the `openai` Python SDK, etc.) at `http://localhost:47871/v1` as the base URL. No API key is required (any non-empty string will satisfy clients that require one).

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
- Adds a **health watchdog** that pings `/api/health` every 60s and relaunches the server if it ever hangs (alive-but-not-responding).

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

Catalog `size_gb` values are **approximate** — derived from the well-known public rule of thumb for 4-bit quantization (~0.5–0.7 GB per billion parameters), not verified against the live Hugging Face API per entry. They're good enough for the UI's download-size hint and hardware-fit calculation, but the actual `/api/cache` and `/api/downloads` endpoints report the real on-disk bytes once a model is downloaded — treat the catalog number as an estimate, not a guarantee.

## License

The launcher scripts in this repo are MIT. Each chat model has its own upstream license (Llama Community License, Apache-2.0 for Qwen/Mistral/DeepSeek-distill, Gemma's terms, MIT for Phi) — check the model card on Hugging Face before commercial use.
