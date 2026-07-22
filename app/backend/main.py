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
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import cache, catalog, settings as app_settings, llm_engine, hub, memory_policy, providers, router, sessions, storage_policy
from .downloads import manager
from .fleet_auth import load_token as load_fleet_token, make_middleware as fleet_middleware, manifest
from .auto_update import UpdateError
from .auto_update_config import create_updater
from .process_title import PROCESS_TITLE, apply_process_title


PROCESS_TITLE_APPLIED = apply_process_title()


# ───────────── App release version ─────────────
# Read once at module load — `VERSION` lives at the project root (a sibling
# of `app/`). Surfaced via `/api/version` for the WebUI footer.

def _read_app_version() -> str:
    try:
        version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
        ver = version_file.read_text().strip()
        return ver
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


class ChatActivityMiddleware:
    """Count complete chat responses, including the lifetime of streams."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        track = (scope.get("type") == "http" and scope.get("method") == "POST" and
                 scope.get("path") in {"/api/chat/completions", "/v1/chat/completions"})
        if track:
            with _CHAT_ACTIVITY_LOCK:
                global _CHAT_ACTIVITY
                _CHAT_ACTIVITY += 1
        try:
            await self.app(scope, receive, send)
        finally:
            if track:
                with _CHAT_ACTIVITY_LOCK:
                    _CHAT_ACTIVITY = max(0, _CHAT_ACTIVITY - 1)


_CHAT_ACTIVITY_LOCK = threading.Lock()
_CHAT_ACTIVITY = 0


app.add_middleware(ChatActivityMiddleware)
app.add_middleware(NoCacheStaticMiddleware)
FLEET_TOKEN = load_fleet_token()
app.middleware("http")(fleet_middleware(FLEET_TOKEN))


# ───────────── request models ─────────────

class StartDownloadBody(BaseModel):
    repo: str
    token: Optional[str] = None


class SettingsBody(BaseModel):
    hf_token: Optional[str] = None
    uninterrupted_mode: Optional[bool] = None
    request_timeout: Optional[int] = Field(None, ge=5, le=300)


class AutoUpdateSettingsBody(BaseModel):
    mode: str
    frequency: str
    maintenance_hour: int
    idle_only: bool = True


class AutoUpdateRequestBody(BaseModel):
    after_current: bool = False


class MemoryPolicyBody(BaseModel):
    mode: str


class TokenTestBody(BaseModel):
    hf_token: Optional[str] = None


class ProviderKeyBody(BaseModel):
    api_key: Optional[str] = Field(None, max_length=16384)


class ProviderPaidBody(BaseModel):
    enabled: bool = False


class SessionBody(BaseModel):
    id: Optional[str] = Field(None, max_length=100)
    title: Optional[str] = Field(None, max_length=200)
    model: Optional[str] = Field(None, max_length=500)
    pinned: Optional[bool] = None
    messages: Optional[list] = Field(None, max_length=500)


class PinBody(BaseModel):
    pinned: bool = True


class RenameBody(BaseModel):
    title: str = Field("", max_length=200)


class ProviderEnabledBody(BaseModel):
    enabled: bool = True


class ProviderOrderBody(BaseModel):
    order: list[str]


class LoadModelBody(BaseModel):
    repo: str = Field(max_length=500)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=1_000_000)


class ChatCompletionsBody(BaseModel):
    repo: str = Field(max_length=500)
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, ge=1, le=32768)
    top_p: float = Field(1.0, gt=0.0, le=1.0)
    stream: bool = True
    exclude_providers: list[str] = Field(default_factory=list, max_length=32)
    images: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("images")
    @classmethod
    def validate_images(cls, images: list[str]) -> list[str]:
        for image in images:
            if image.startswith(("http://", "https://")):
                raise ValueError("remote image URLs are not accepted; upload image data")
            if len(image) > 14_000_000:
                raise ValueError("each encoded image must be 10 MB or smaller")
        return images


class OpenAIChatCompletionsBody(BaseModel):
    """OpenAI-schema alias of ChatCompletionsBody — uses `model` instead of
    `repo` so existing OpenAI-client tooling (Continue.dev, Open WebUI, etc.)
    can point at this server as a drop-in `/v1` base URL."""
    model: str = Field(max_length=500)
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, ge=1, le=32768)
    top_p: float = Field(1.0, gt=0.0, le=1.0)
    stream: bool = False


def _automatic_update_blockers() -> list[str]:
    reasons: list[str] = []
    with _CHAT_ACTIVITY_LOCK:
        if _CHAT_ACTIVITY:
            reasons.append("a chat response is queued or streaming")
    if llm_engine.manager.is_busy() and not reasons:
        reasons.append("a model is loading or generating")
    states = {str(job.state) for job in manager.list_jobs()}
    if states & {"queued", "running", "paused", "cancelling"}:
        reasons.append("a model download is active")
    return reasons


auto_updater = create_updater(readiness=_automatic_update_blockers)
memory_policy.start_background(
    llm_engine.manager,
    active_check=lambda: bool(_CHAT_ACTIVITY),
)


# ───────────── API: meta ─────────────

@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": app.version,
        "app_version": APP_VERSION,
        "hf_home": str(cache.hf_home()),
        "hub_dir": str(cache.hub_dir()),
        # Local-model memory status (drives the Unload button + idle notice).
        "loaded_model": llm_engine.manager.loaded_repo(),
        "idle_seconds": llm_engine.manager.idle_seconds(),
        "auto_unload": llm_engine.manager.last_auto_unload(),
    }


@app.get("/api/capabilities")
def capabilities() -> dict:
    return manifest(modality="chat", title=app.title, version=APP_VERSION,
                    operations=["chat", "vision", "openai_compatible"],
                    diagnostics="/api/chat/diagnostics")


# ── Update / generation health (auto-check surfaced by the web-UI banner) ──
# Detect-in-app, apply-via-sidebar: the frontend banner reads this and points
# the user at the single "Update" (or "Install Generation") button in the
# Pinokio sidebar. We never git-pull from here — a sandboxed web page can't
# reliably drive Pinokio's script runner, and the backend restarting itself
# mid-request is fragile.
import importlib.util as _ilu
import threading as _threading
import time as _time
import urllib.request as _urlreq

_UPDATE_REPO = "theng12/chatstudio-mac"
_GEN_MODULE = "mlx_lm"
_update_state = {"checked_at": 0.0, "latest": None}


def _parse_ver(v):
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("v").split(".")[:3])
    except Exception:
        return (0,)


def _refresh_latest_version():
    try:
        url = f"https://raw.githubusercontent.com/{_UPDATE_REPO}/main/VERSION"
        with _urlreq.urlopen(url, timeout=5) as r:
            _update_state["latest"] = r.read().decode("utf-8").strip()
    except Exception:
        pass
    finally:
        _update_state["checked_at"] = _time.time()


@app.get("/api/update-status")
def update_status() -> dict:
    """What the web-UI banner needs: are we behind the published version, and is
    the generation stack actually installed? The remote version is fetched from
    the repo's raw VERSION file at most every ~6h, in a background thread, so a
    slow or unreachable GitHub never blocks the request."""
    if _time.time() - _update_state["checked_at"] > 6 * 3600:
        _threading.Thread(target=_refresh_latest_version, daemon=True).start()
    latest = _update_state["latest"]
    behind = bool(latest and _parse_ver(latest) > _parse_ver(APP_VERSION))
    gen_required = _GEN_MODULE is not None
    gen_ok = (_ilu.find_spec(_GEN_MODULE) is not None) if gen_required else None
    return {
        "app_version": APP_VERSION,
        "latest_version": latest,
        "update_available": behind,
        "generation_required": gen_required,
        "generation_ok": gen_ok,
    }


@app.get("/api/version")
def app_release_version() -> dict:
    return {
        "app_version": APP_VERSION,
        "title": app.title,
    }


@app.get("/api/release-notes")
def release_notes() -> dict:
    """Return the current release notes from the checked-out CHANGELOG.

    Keeping this server-side makes the in-app What's New panel follow the
    actual installed release instead of a separately maintained frontend list.
    Markdown is returned as plain strings; the frontend renders it with
    textContent via Alpine, so model/release text cannot become HTML.
    """
    try:
        changelog = Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
    except OSError:
        return {"current_version": APP_VERSION, "releases": []}

    releases = []
    sections = re.split(r"(?m)^##\s+", text)[1:]
    for section in sections:
        lines = section.splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        match = re.search(r"\d+\.\d+\.\d+", heading)
        if not match:
            continue
        details = []
        for line in lines[1:]:
            value = line.strip()
            if value.startswith("- "):
                details.append(re.sub(r"[`*]", "", value[2:].strip()))
            elif value.startswith("### "):
                details.append(re.sub(r"[`*]", "", value[4:].strip()))
            if len(details) >= 12:
                break
        releases.append({
            "version": match.group(0),
            "heading": heading,
            "details": details,
        })
        if len(releases) >= 8:
            break
    return {"current_version": APP_VERSION, "releases": releases}


@app.get("/api/auto-update/status")
def automatic_update_status() -> dict:
    return auto_updater.public_status()


@app.get("/api/auto-update/readiness")
def automatic_update_readiness() -> dict:
    return auto_updater.readiness_status()


@app.post("/api/auto-update/settings")
def automatic_update_settings(body: AutoUpdateSettingsBody) -> dict:
    try:
        return auto_updater.save_settings(body.model_dump())
    except UpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auto-update/check")
def automatic_update_check() -> dict:
    try:
        return auto_updater.trigger_check()
    except UpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/auto-update/update")
def automatic_update_run(body: AutoUpdateRequestBody) -> dict:
    try:
        return auto_updater.trigger_update(after_current=body.after_current)
    except UpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/auto-update/retry")
def automatic_update_retry() -> dict:
    try:
        return auto_updater.retry()
    except UpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
        revision = cache.snapshot_revision(m.repo)
        if revision is not None and not llm_engine.is_vision_model(m.repo):
            d["runtime_revision"] = revision
            d["max_output_tokens"] = 32768
            d["verified_token_usage"] = True
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
    if body.uninterrupted_mode is not None:
        app_settings.set_uninterrupted(body.uninterrupted_mode)
    if body.request_timeout is not None:
        app_settings.set_request_timeout(body.request_timeout)
    return app_settings.serialize_public()


@app.get("/api/storage-policy")
def get_storage_policy() -> dict:
    return storage_policy.status()


@app.put("/api/storage-policy")
def put_storage_policy(body: dict) -> dict:
    storage_policy.save(body.get("enabled"), body.get("retention_days"), body.get("max_gb"))
    return storage_policy.status()


@app.post("/api/storage-policy/cleanup")
def cleanup_storage_policy(body: dict | None = None) -> dict:
    target = (body or {}).get("target_bytes")
    if target is not None and (not isinstance(target, int) or target < 0):
        raise HTTPException(400, "target_bytes must be a non-negative integer")
    return storage_policy.cleanup()


@app.get("/api/memory-policy")
def get_memory_policy() -> dict:
    return {**memory_policy.status(), "process_title": PROCESS_TITLE,
            "process_title_applied": PROCESS_TITLE_APPLIED}


@app.put("/api/memory-policy")
def put_memory_policy(body: MemoryPolicyBody) -> dict:
    memory_policy.save(body.mode)
    return get_memory_policy()


@app.post("/api/memory/release")
def release_memory() -> dict:
    return {
        **memory_policy.release_now(),
        "process_title": PROCESS_TITLE,
        "process_title_applied": PROCESS_TITLE_APPLIED,
    }


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


# ───────────── API: cloud providers ─────────────

@app.get("/api/providers")
def list_providers() -> dict:
    """List configured cloud providers + their free models. Never exposes raw
    API keys — only a masked preview + key_set boolean."""
    return {"providers": providers.public_view()}


@app.post("/api/providers/{name}/key")
def set_provider_key(name: str, body: ProviderKeyBody) -> dict:
    if name not in providers.PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    app_settings.set_provider_key(name, body.api_key)
    return {"ok": True, "providers": providers.public_view()}


@app.get("/api/providers/{name}/models/live")
async def provider_live_models(name: str) -> dict:
    """Fetch the provider's current model catalog live from its /models
    endpoint — so the dropdown can show what's actually available now instead
    of the curated (drift-prone) list."""
    if name not in providers.PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    try:
        models = await providers.list_live_models(providers.PROVIDERS[name])
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Live model fetch failed: {e}")
    return {"provider": name, "count": len(models), "models": models}


# ───────────── API: router (Uninterrupted Mode priority + health) ─────────────

@app.get("/api/router/providers")
def router_providers() -> dict:
    """Routable providers (local + cloud) in priority order, with enabled/key
    state — drives the fallback-order + health UI."""
    return {
        "providers": router.ordered_provider_list(),
        "uninterrupted_mode": app_settings.get_uninterrupted(),
        "request_timeout": app_settings.get_request_timeout(),
    }


@app.get("/api/router/health")
async def router_health() -> dict:
    return {"health": await router.health_check_all()}


@app.post("/api/router/order")
def router_set_order(body: ProviderOrderBody) -> dict:
    app_settings.set_provider_priority(body.order)
    return {"ok": True, "providers": router.ordered_provider_list()}


@app.post("/api/router/providers/{pid}/enabled")
def router_set_enabled(pid: str, body: ProviderEnabledBody) -> dict:
    app_settings.set_provider_enabled(pid, body.enabled)
    return {"ok": True, "providers": router.ordered_provider_list()}


@app.post("/api/providers/{name}/paid")
def set_provider_paid(name: str, body: ProviderPaidBody) -> dict:
    """Opt in/out of a provider's paid models. When off, paid models are hidden
    from the UI and rejected by the chat route."""
    if name not in providers.PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    app_settings.set_provider_paid(name, body.enabled)
    return {"ok": True, "providers": providers.public_view()}


# ───────────── API: chat sessions (history) ─────────────

@app.get("/api/sessions")
def list_sessions(q: str = "") -> dict:
    """Session metadata (pinned first, then recent). `q` searches title + content."""
    return {"sessions": sessions.list_meta(q)}


@app.get("/api/sessions/{sid}")
def get_session(sid: str) -> dict:
    s = sessions.get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    return s


@app.post("/api/sessions")
def save_session(body: SessionBody) -> dict:
    return sessions.upsert(body.model_dump(exclude_none=True))


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str) -> dict:
    return {"deleted": sessions.delete(sid)}


@app.post("/api/sessions/{sid}/pin")
def pin_session(sid: str, body: PinBody) -> dict:
    if not sessions.set_pinned(sid, body.pinned):
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@app.post("/api/sessions/{sid}/rename")
def rename_session(sid: str, body: RenameBody) -> dict:
    if not sessions.rename(sid, body.title):
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@app.post("/api/providers/{name}/test")
async def test_provider_key(name: str, body: ProviderKeyBody) -> dict:
    if name not in providers.PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    p = providers.PROVIDERS[name]
    token = (body.api_key or "").strip() or providers.get_api_key(name)
    if not token:
        raise HTTPException(status_code=400, detail=f"No {p.name} API key provided.")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{p.base_url}/models",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 200:
            data = r.json()
            model_count = len(data.get("data", [])) if isinstance(data, dict) else 0
            return {"ok": True, "models_available": model_count}
        return {"ok": False, "status": r.status_code, "detail": r.text[:300]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Test failed: {e}")


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


@app.post("/api/chat/cancel")
def chat_cancel() -> dict:
    """Stop the in-flight generation (Stop button). Frees the worker so the
    next message can start immediately instead of waiting out max_tokens."""
    return {"ok": llm_engine.manager.cancel()}


@app.post("/api/chat/unload")
def chat_unload() -> dict:
    """Free the loaded local model from unified memory (Unload button)."""
    result = memory_policy.release_now()
    details = result.get("last_release_details") or {}
    return {"unloaded": bool(details.get("released")), "repo": details.get("repo")}


@app.on_event("startup")
async def _prune_stale_partials():
    # Reclaim disk from orphaned .incomplete download partials left by earlier
    # interrupted sessions. Runs once, off-thread so it can't delay startup.
    async def _sweep():
        try:
            freed = await asyncio.to_thread(cache.prune_all_incomplete)
            if freed:
                print(f"[chat studio] pruned {freed / 1e9:.2f} GB of stale "
                      f"download partials on startup", file=sys.stderr, flush=True)
        except Exception:
            pass
    asyncio.create_task(_sweep())


@app.post("/api/chat/completions")
async def chat_completions(body: ChatCompletionsBody):
    messages = [m.model_dump() for m in body.messages]

    # ── Uninterrupted Mode: route through the auto-fallback router ──
    if app_settings.get_uninterrupted():
        params = {"temperature": body.temperature, "max_tokens": body.max_tokens, "top_p": body.top_p}
        timeout = app_settings.get_request_timeout()
        exclude = body.exclude_providers or []
        if body.stream:
            async def uninterrupted_stream():
                meta = None
                async for ev in router.generate(messages, body.repo, params, uninterrupted=True, timeout=timeout, exclude_ids=exclude):
                    t = ev.get("type")
                    if t == "chunk":
                        yield ev["text"]
                    elif t == "done":
                        meta = {"provider": ev["provider"], "model": ev["model"], "fallback": ev["fallback"]}
                    elif t == "interrupted":
                        # Stream broke AFTER text — keep the partial; the UI shows
                        # a "Continue with fallback" button (no inline noise).
                        meta = {"interrupted": True, "provider": ev["provider"], "provider_id": ev.get("provider_id")}
                    elif t == "error":
                        yield f"\n[error] {ev.get('detail', 'generation failed')}"
                # Trailing metadata sentinel — the UI strips this and shows which
                # provider answered / whether it fell back / was interrupted.
                if meta is not None:
                    yield "\n__CHATSTUDIO_META__" + json.dumps(meta)
            return StreamingResponse(uninterrupted_stream(), media_type="text/plain")
        # non-streaming
        text, meta = "", None
        async for ev in router.generate(messages, body.repo, params, uninterrupted=True, timeout=timeout, exclude_ids=exclude):
            t = ev.get("type")
            if t == "chunk":
                text += ev["text"]
            elif t == "done":
                meta = {"provider": ev["provider"], "model": ev["model"], "fallback": ev["fallback"]}
            elif t in ("error", "interrupted"):
                raise HTTPException(status_code=502, detail=ev.get("detail", "generation failed"))
        return {"repo": body.repo, "content": text, "meta": meta}

    # Cloud provider routing — synthetic repo id `provider:<key>:<model_id>`.
    if body.repo.startswith("provider:"):
        parsed = providers.parse_repo(body.repo)
        if not parsed:
            raise HTTPException(status_code=400, detail=f"Unknown provider repo: {body.repo}")
        provider, model = parsed
        # Gate paid models: refuse unless the user enabled paid for this
        # provider, so a paid model can't be used (and billed) by accident.
        if not providers.model_allowed(provider, model):
            raise HTTPException(
                status_code=403,
                detail=(f"{model.id} is a paid {provider.name} model. "
                        f"Enable paid models for {provider.name} in Settings → Cloud providers first."),
            )
        if body.stream:
            async def event_stream():
                try:
                    async for chunk in providers.stream_chat(
                        provider, model, messages,
                        body.temperature, body.max_tokens, body.top_p,
                    ):
                        yield chunk
                except Exception as e:
                    import traceback
                    print(f"[chat studio] cloud stream error:\n{traceback.format_exc()}",
                          file=sys.stderr, flush=True)
                    yield f"\n[error] {type(e).__name__}: {e}\n"
            return StreamingResponse(event_stream(), media_type="text/plain")
        # Non-streaming: collect chunks
        try:
            chunks = []
            async for c in providers.stream_chat(
                provider, model, messages,
                body.temperature, body.max_tokens, body.top_p,
            ):
                chunks.append(c)
            return {"repo": body.repo, "content": "".join(chunks)}
        except Exception as e:
            # str(e) alone is EMPTY for httpx timeouts — always include the
            # exception type so the client never sees a bodyless 502, and
            # log it (with the model) so the failure is visible server-side.
            detail = f"{provider.name} · {model.id}: {type(e).__name__}: {e}".rstrip(": ")
            print(f"[chat studio] cloud error (api): {detail}", file=sys.stderr, flush=True)
            raise HTTPException(status_code=502, detail=detail)

    # Auto-load the requested local model if it's cached but not loaded
    # (off the event loop so a multi-GB load doesn't stall other requests).
    try:
        await asyncio.to_thread(llm_engine.manager.ensure_loaded, body.repo)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if body.stream:
        # A *sync* generator: Starlette iterates it in a threadpool, so the
        # blocking MLX stream never stalls the event loop. (The MLX work itself
        # runs on the engine's dedicated worker thread — see llm_engine.)
        def event_stream():
            try:
                for chunk in llm_engine.manager.stream_chat(
                    body.repo, messages, body.temperature, body.max_tokens, body.top_p,
                    body.images,
                ):
                    yield chunk
            except Exception as e:
                import traceback
                print(f"[chat studio] stream error:\n{traceback.format_exc()}",
                      file=sys.stderr, flush=True)
                yield f"\n[error] {type(e).__name__}: {e}\n"

        return StreamingResponse(event_stream(), media_type="text/plain")

    try:
        text = llm_engine.manager.chat_once(
            body.repo, messages, body.temperature, body.max_tokens, body.top_p,
            body.images,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"repo": body.repo, "content": text}


# ───────────── API: OpenAI-compatible alias ─────────────

@app.get("/v1/models")
async def openai_models() -> dict:
    # Local MLX models first — every cached model is usable (catalog entries
    # plus anything the user downloaded via Hub search).
    seen: set[str] = set()
    data: list[dict] = []
    for m in catalog.CATALOG:
        if cache.cache_state(m.repo) == "cached" and m.repo not in seen:
            data.append({"id": m.repo, "object": "model", "owned_by": m.repo.split("/")[0]})
            seen.add(m.repo)
    for repo in cache.list_cached_repos():
        if repo not in seen:
            data.append({"id": repo, "object": "model", "owned_by": repo.split("/")[0]})
            seen.add(repo)

    # Cloud providers: include any provider whose API key is configured
    # (env var or settings.json — `get_api_key` handles the precedence,
    # including HF Router's fallback to the saved HF token). Providers
    # without a key are silently excluded — no key, no models.
    keyed_providers = [
        p for p in providers.PROVIDERS.values() if providers.get_api_key(p.key)
    ]
    if keyed_providers:
        # Fan out concurrently so the slowest provider doesn't dominate
        # wall-clock. `return_exceptions=True` ensures one provider's
        # failure (network, auth, upstream 5xx) never breaks /v1/models —
        # we just skip that provider for this call. `models_for_provider`
        # already swallows its own exceptions and falls back to the static
        # catalog, so the outer return_exceptions is belt-and-braces.
        results = await asyncio.gather(
            *(providers.models_for_provider(p) for p in keyed_providers),
            return_exceptions=True,
        )
        for provider, result in zip(keyed_providers, results):
            if isinstance(result, BaseException):
                continue
            for m in result:
                repo = m["repo"]
                if repo in seen:
                    continue
                data.append({"id": repo, "object": "model", "owned_by": provider.key})
                seen.add(repo)

    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def openai_chat_completions(body: OpenAIChatCompletionsBody):
    messages = [m.model_dump() for m in body.messages]
    created = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    # ── Cloud provider routing: synthetic id "provider:<key>:<model_id>" ──
    # Mirrors /api/chat/completions' cloud fork so /v1/chat/completions is a
    # drop-in for clients picking cloud models from /v1/models. Without this
    # fork, ensure_loaded() below would raise a 409 for any cloud model id.
    if body.model.startswith("provider:"):
        parsed = providers.parse_repo(body.model)
        if not parsed:
            raise HTTPException(status_code=400, detail=f"Unknown provider model: {body.model}")
        provider, model = parsed
        # No key → can't reach upstream. Surface a clean 401 instead of letting
        # providers.stream_chat raise a generic RuntimeError mid-stream.
        if not providers.get_api_key(provider.key):
            raise HTTPException(
                status_code=401,
                detail=f"{provider.name} API key not set. Add it in Settings → Cloud providers.",
            )
        # Paid models are gated behind the per-provider opt-in so a paid model
        # can't be used (and billed) without the user explicitly enabling it.
        if not providers.model_allowed(provider, model):
            raise HTTPException(
                status_code=403,
                detail=(f"{model.id} is a paid {provider.name} model. "
                        f"Enable paid models for {provider.name} in Settings → Cloud providers first."),
            )
        if body.stream:
            async def cloud_event_stream():
                try:
                    async for chunk in providers.stream_chat(
                        provider, model, messages,
                        body.temperature, body.max_tokens, body.top_p,
                    ):
                        event = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": body.model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": chunk},
                                "finish_reason": None,
                            }],
                        }
                        yield f"data: {json.dumps(event)}\n\n"
                except Exception as e:
                    # Match the local-path error envelope so OpenAI clients
                    # parse cloud and local failures the same way.
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
                        "error": str(e),
                    }
                    yield f"data: {json.dumps(event)}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(cloud_event_stream(), media_type="text/event-stream")
        # Non-streaming: collect chunks and return a single chat.completion.
        try:
            chunks: list[str] = []
            async for c in providers.stream_chat(
                provider, model, messages,
                body.temperature, body.max_tokens, body.top_p,
            ):
                chunks.append(c)
            text = "".join(chunks)
        except Exception as e:
            # str(e) alone is EMPTY for httpx timeouts (this is exactly the
            # "502 (No body)" clients used to see when NVIDIA hung on a big
            # model) — always include the exception type, and log server-side
            # with the model id so /v1 failures show up in the service log.
            detail = f"{provider.name} · {model.id}: {type(e).__name__}: {e}".rstrip(": ")
            print(f"[chat studio] cloud error (v1): {detail}", file=sys.stderr, flush=True)
            raise HTTPException(status_code=502, detail=detail)
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

    # Drop-in OpenAI behavior: load the requested model on demand if needed, so
    # clients (e.g. Story Studio) just specify `model` without a separate load.
    try:
        await asyncio.to_thread(llm_engine.manager.ensure_loaded, body.model)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

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
        result = llm_engine.manager.chat_once_with_usage(
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
            "message": {"role": "assistant", "content": result.text},
            "finish_reason": result.finish_reason,
        }],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
        },
        "usage_verified": True,
        "model_revision": cache.snapshot_revision(body.model),
    }


# ───────────── API: dependency repair ─────────────

@app.post("/api/deps/install")
async def install_deps():
    """Re-run `pip install -r requirements.txt` inside the current
    Python environment. Blocking call pushed to a thread executor so the
    event loop stays responsive while pip downloads + compiles."""
    app_dir = Path(__file__).resolve().parent.parent
    req = app_dir / "requirements.txt"
    install_args = [sys.executable, "-m", "pip", "install", "-r", str(req)]

    loop = asyncio.get_event_loop()

    def _run() -> dict:
        try:
            r = subprocess.run(
                install_args,
                capture_output=True, text=True, timeout=600,
                cwd=str(app_dir),
            )
            return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": "timed out after 10 minutes"}
        except Exception as e:
            return {"ok": False, "stdout": "", "stderr": str(e)}

    return await loop.run_in_executor(None, _run)


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
