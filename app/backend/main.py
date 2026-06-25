"""
Chat Studio (Mac) — backend.

Serves:
- `/`                          → single-page UI
- `/api/health`                → liveness check
- `/api/catalog`                → MLX chat-model catalog with cache state
- `/api/cache/{repo}`          → cache state for one repo
- `/api/downloads*`            → list/start/cancel + SSE stream
- `/api/settings*`             → HF token + future settings
- `/api/connectivity`          → bind port, local IPs, share-proxy state
- `/api/chat/models`           → cached/loadable chat models
- `/api/chat/load`             → load a model into memory (unloads previous)
- `/api/chat/completions`      → turn-based chat, streamed
- `/api/chat/diagnostics`      → mlx / mlx_lm availability + loaded model
- `/v1/chat/completions`       → OpenAI-compatible alias
- `/v1/models`                 → OpenAI-compatible model listing
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import cache, catalog, settings as app_settings, llm_engine, hub
from .downloads import manager


# ───────────── App release version ─────────────
# Read once at module load — `VERSION` lives at the project root (a sibling
# of `app/`). Surfaced via `/api/version` for the WebUI footer.

def _read_app_version() -> str:
    try:
        version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_file.read_text().strip()
    except Exception:
        return "unknown"

APP_VERSION = _read_app_version()


# ───────────── FastAPI setup ─────────────

app = FastAPI(title="Chat Studio KH", version="0.1.0")

# Permissive CORS so the main mac can call the mac mini over LAN, and so
# OpenAI-compatible clients (Continue.dev, Open WebUI, etc.) can hit /v1 from
# anywhere on the network.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """
    Force the Pinokio webview (and any browser) to always re-fetch the static
    frontend. Pinokio's embedded webview can cache index.html / app.js / style.css
    very aggressively, so we explicitly disable caching for the frontend files
    and any /assets/* path.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/assets") or path.endswith(
            (".html", ".js", ".css")
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheStaticMiddleware)


# ───────────── request models ─────────────

class StartDownloadBody(BaseModel):
    repo: str
    token: Optional[str] = None


class SettingsBody(BaseModel):
    hf_token: Optional[str] = None


class TokenTestBody(BaseModel):
    hf_token: Optional[str] = None


class LoadModelBody(BaseModel):
    repo: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionsBody(BaseModel):
    repo: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    stream: bool = True


class OpenAIChatCompletionsBody(BaseModel):
    """OpenAI-schema alias of ChatCompletionsBody — uses `model` instead of
    `repo` so existing OpenAI-client tooling (Continue.dev, Open WebUI, etc.)
    can point at this server as a drop-in `/v1` base URL."""
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    stream: bool = False


# ───────────── API: meta ─────────────

@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": app.version,
        "app_version": APP_VERSION,
        "hf_home": str(cache.hf_home()),
        "hub_dir": str(cache.hub_dir()),
    }


@app.get("/api/version")
def app_release_version() -> dict:
    return {
        "app_version": APP_VERSION,
        "title": app.title,
    }


@app.get("/api/system")
def system_hardware() -> dict:
    """Apple Silicon chip + unified memory snapshot of the host. Frontend uses
    this for the Models tab per-model fit chip. Mac-only — the underlying
    sysctl probes return None elsewhere."""
    from . import system_info
    return system_info.system_info()


# ───────────── API: catalog ─────────────

@app.get("/api/catalog")
def get_catalog() -> dict:
    families = {fid: catalog.serialize_family(f) for fid, f in catalog.FAMILIES.items()}
    models = []
    for m in catalog.CATALOG:
        d = catalog.serialize_model(m)
        d["cache"] = cache.status_snapshot(m.repo)
        active = manager.active_for_repo(m.repo)
        d["active_download"] = active.serialize() if active else None
        models.append(d)
    return {"families": families, "models": models}


@app.get("/api/cache/{repo:path}")
def get_cache(repo: str) -> dict:
    return cache.status_snapshot(repo)


# ───────────── API: Hugging Face Hub search ─────────────

@app.get("/api/hub/search")
def hub_search(q: str = "", limit: int = 40) -> dict:
    """Search the Hugging Face Hub for MLX models (beyond the curated catalog),
    annotated with this server's local cache state so the UI can show
    download / cached / chat-ready status inline."""
    catalog_repos = {m.repo for m in catalog.CATALOG}
    try:
        results = hub.search(q, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hub search failed: {e}")
    out = []
    for r in results:
        repo = r["repo"]
        active = manager.active_for_repo(repo)
        out.append({
            **r,
            "cache_state": cache.cache_state(repo),
            "in_catalog": repo in catalog_repos,
            "active_download": active.serialize() if active else None,
        })
    return {"query": q, "models": out}


# ───────────── API: downloads ─────────────

@app.get("/api/downloads")
def list_downloads() -> dict:
    return {"jobs": [j.serialize() for j in manager.list_jobs()]}


@app.delete("/api/downloads")
def clear_downloads() -> dict:
    return {"cleared": manager.clear_finished()}


@app.post("/api/downloads")
def start_download(body: StartDownloadBody) -> dict:
    if not body.repo or "/" not in body.repo:
        raise HTTPException(status_code=400, detail="repo must be 'owner/name'")
    job = manager.start(body.repo, token=body.token)
    return {"job": job.serialize()}


@app.delete("/api/downloads/{job_id}")
def cancel_download(job_id: str) -> dict:
    ok = manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found or already finished")
    job = manager.get(job_id)
    return {"job": job.serialize() if job else None}


@app.get("/api/downloads/stream")
async def stream_downloads():
    from sse_starlette.sse import EventSourceResponse
    async def stream():
        try:
            while True:
                payload = {"jobs": [j.serialize() for j in manager.list_jobs()]}
                yield {"event": "snapshot", "data": json.dumps(payload)}
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return
    return EventSourceResponse(stream())


# ───────────── API: settings ─────────────

@app.get("/api/settings")
def get_settings() -> dict:
    return app_settings.serialize_public()


@app.post("/api/settings")
def update_settings(body: SettingsBody) -> dict:
    if body.hf_token is not None:
        app_settings.set_hf_token(body.hf_token)
    return app_settings.serialize_public()


@app.post("/api/settings/test-hf-token")
def test_hf_token(body: TokenTestBody) -> dict:
    token = (body.hf_token or "").strip() or app_settings.get_hf_token()
    if not token:
        raise HTTPException(status_code=400, detail="No token provided and none saved.")
    try:
        from huggingface_hub import HfApi
        info = HfApi().whoami(token=token)
        return {
            "ok": True,
            "name": info.get("name") or info.get("fullname") or info.get("email"),
            "type": info.get("type"),
            "orgs": [o.get("name") for o in (info.get("orgs") or []) if o.get("name")],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token validation failed: {e}")


# ───────────── API: connectivity ─────────────

def _classify_ip(ip: str) -> str:
    if ip.startswith("127."):
        return "loopback"
    try:
        octets = [int(x) for x in ip.split(".")]
        if len(octets) == 4 and octets[0] == 100 and 64 <= octets[1] <= 127:
            return "tailscale"
    except (ValueError, IndexError):
        pass
    if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
        return "lan"
    return "other"


def _list_local_ips() -> list[dict]:
    ips: set[str] = set()
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except (socket.error, OSError):
        pass
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ips.add(sock.getsockname()[0])
    except OSError:
        pass
    finally:
        sock.close()
    out = [{"ip": ip, "kind": _classify_ip(ip)} for ip in ips if ":" not in ip]
    rank = {"tailscale": 0, "lan": 1, "other": 2, "loopback": 3}
    out.sort(key=lambda d: (rank.get(d["kind"], 9), d["ip"]))
    return out


def _detect_bind_port(default: int = 47871) -> int:
    args = sys.argv
    try:
        i = args.index("--port")
        return int(args[i + 1])
    except (ValueError, IndexError):
        pass
    env_port = os.environ.get("UVICORN_PORT", "").strip()
    if env_port.isdigit():
        return int(env_port)
    return default


def _detect_bind_host(default: str = "0.0.0.0") -> str:
    args = sys.argv
    try:
        i = args.index("--host")
        return args[i + 1]
    except (ValueError, IndexError):
        pass
    return default


_BIND_PORT = _detect_bind_port()
_BIND_HOST = _detect_bind_host()


@app.get("/api/connectivity")
def connectivity(request: Request) -> dict:
    request_port = request.url.port
    if request_port is None:
        request_port = 443 if request.url.scheme == "https" else 80
    return {
        "listen_port": _BIND_PORT,
        "bind_port": _BIND_PORT,
        "bind_host": _BIND_HOST,
        "request_port": request_port,
        "scheme": request.url.scheme,
        "client_url": str(request.base_url).rstrip("/"),
        "addresses": _list_local_ips(),
        "share_local_enabled": (os.environ.get("PINOKIO_SHARE_LOCAL", "").strip().lower() == "true"),
        "share_local_port_fixed": os.environ.get("PINOKIO_SHARE_LOCAL_PORT", "").strip() or None,
        "share_passcode_set": bool(os.environ.get("PINOKIO_SHARE_PASSCODE", "").strip()),
        "pinokio_ui_port": 42000,
    }


# ───────────── API: chat ─────────────

@app.get("/api/chat/diagnostics")
def chat_diagnostics() -> dict:
    data = llm_engine.diagnostics()
    data["app_version"] = APP_VERSION
    return data


@app.get("/api/chat/models")
def chat_models() -> dict:
    return {"models": llm_engine.list_chat_models()}


@app.post("/api/chat/load")
def chat_load(body: LoadModelBody) -> dict:
    # Any fully-cached model is loadable — both curated-catalog models and ones
    # the user downloaded via Hub search. An unknown, not-cached repo is a 400.
    if cache.cache_state(body.repo) != "cached":
        if catalog.get_model(body.repo) is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model {body.repo}. Download it first (Models → search).",
            )
        raise HTTPException(
            status_code=409,
            detail=f"Model {body.repo} is not fully cached. Download it from the Models tab first.",
        )
    try:
        result = llm_engine.manager.load(body.repo)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return result


@app.post("/api/chat/completions")
async def chat_completions(body: ChatCompletionsBody):
    messages = [m.model_dump() for m in body.messages]

    if body.stream:
        async def event_stream():
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def producer():
                try:
                    llm_engine._init_metal()
                    for chunk in llm_engine.manager.stream_chat(
                        body.repo, messages, body.temperature, body.max_tokens, body.top_p,
                    ):
                        asyncio.run_coroutine_threadsafe(queue.put(("chunk", chunk)), loop)
                    asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(queue.put(("error", str(e))), loop)

            import threading
            threading.Thread(target=producer, daemon=True).start()

            while True:
                kind, payload = await queue.get()
                if kind == "chunk":
                    yield payload
                elif kind == "error":
                    yield f"\n[error] {payload}\n"
                    break
                else:
                    break

        return StreamingResponse(event_stream(), media_type="text/plain")

    try:
        text = llm_engine.manager.chat_once(
            body.repo, messages, body.temperature, body.max_tokens, body.top_p,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"repo": body.repo, "content": text}


# ───────────── API: OpenAI-compatible alias ─────────────

@app.get("/v1/models")
def openai_models() -> dict:
    # Every cached model is usable — catalog entries plus anything the user
    # downloaded via Hub search.
    repos: list[str] = []
    seen = set()
    for m in catalog.CATALOG:
        if cache.cache_state(m.repo) == "cached" and m.repo not in seen:
            repos.append(m.repo); seen.add(m.repo)
    for repo in cache.list_cached_repos():
        if repo not in seen:
            repos.append(repo); seen.add(repo)
    data = [{"id": r, "object": "model", "owned_by": r.split("/")[0]} for r in repos]
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def openai_chat_completions(body: OpenAIChatCompletionsBody):
    messages = [m.model_dump() for m in body.messages]
    created = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    if body.stream:
        async def event_stream():
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def producer():
                try:
                    for chunk in llm_engine.manager.stream_chat(
                        body.model, messages, body.temperature, body.max_tokens, body.top_p,
                    ):
                        asyncio.run_coroutine_threadsafe(queue.put(("chunk", chunk)), loop)
                    asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(queue.put(("error", str(e))), loop)

            import threading
            threading.Thread(target=producer, daemon=True).start()

            while True:
                kind, payload = await queue.get()
                if kind == "chunk":
                    event = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": body.model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": payload},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                elif kind == "error":
                    event = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": body.model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "error",
                        }],
                        "error": payload,
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                    break
                else:
                    break
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        text = llm_engine.manager.chat_once(
            body.model, messages, body.temperature, body.max_tokens, body.top_p,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": body.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        },
    }


# ───────────── static frontend ─────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR), html=False), name="assets")

    @app.get("/", response_class=Response)
    def index() -> Response:
        # Read index.html and substitute __APP_VERSION__ tokens with the
        # current VERSION. Auto-bumps cache-buster query strings on every
        # release so users never see stale JS/CSS in Pinokio's aggressively-
        # caching webview.
        html = (FRONTEND_DIR / "index.html").read_text()
        html = html.replace("__APP_VERSION__", APP_VERSION)
        return Response(content=html, media_type="text/html")
