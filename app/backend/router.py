"""
LLM router with automatic fallback ("Uninterrupted Mode").

Tries the user's selected model first, and — when Uninterrupted Mode is on —
automatically falls back to other providers in priority order if the chosen one
fails (offline, rate-limited, overloaded, timed out, model not loaded, empty
response, or a stream that breaks before any text appears).

Design notes
- Modular on purpose: this is a standalone service so Story Studio / batch jobs
  can reuse the same fallback logic, not just the chat UI.
- Unifies two backends behind one async stream: cloud providers (`providers`,
  already async) and the built-in local MLX engine (`llm_engine`, sync on a
  worker thread — bridged to async here).
- `generate()` is an async generator of small event dicts:
    {"type":"chunk","text": "..."}
    {"type":"done","provider_id","provider","model","fallback": bool}
    {"type":"interrupted","provider","detail"}   # stream broke AFTER text
    {"type":"error","detail", ...}                # nothing worked
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import httpx

from . import cache, llm_engine, providers, settings as app_settings

# Limits (per the spec)
GLOBAL_MAX_ATTEMPTS = 5
PER_PROVIDER_RETRIES = 2
BACKOFF_SECONDS = [1, 2, 4]


class _EmptyResponse(Exception):
    """A candidate completed its stream without producing any text."""


@dataclass
class Candidate:
    id: str        # "local" or a provider key
    name: str      # display name
    model: str     # repo id (local) or model id (cloud)
    kind: str      # "local" | "cloud"


# ───────────── candidate building ─────────────

def _default_order() -> list[str]:
    # Local first (free, private, fast), then cloud providers in catalog order.
    return ["local"] + list(providers.PROVIDERS.keys())


def _local_default_model() -> Optional[str]:
    repo = llm_engine.manager.loaded_repo()
    if repo:
        return repo
    cached = cache.list_cached_repos()
    return cached[0] if cached else None


def _provider_default_model(pkey: str) -> Optional[str]:
    p = providers.PROVIDERS.get(pkey)
    if not p or not p.models:
        return None
    free = [m for m in p.models if m.free]
    return (free[0] if free else p.models[0]).id


def _parse_preferred(repo: Optional[str]) -> Optional[Candidate]:
    if not repo:
        return None
    if repo.startswith("provider:"):
        parsed = providers.parse_repo(repo)
        if not parsed:
            return None
        prov, model = parsed
        return Candidate(prov.key, prov.name, model.id, "cloud")
    return Candidate("local", "Local (MLX)", repo, "local")


def build_candidates(preferred_repo: Optional[str], *, fallback: bool) -> list[Candidate]:
    """The ordered list of (provider, model) attempts. Preferred first; then —
    only when fallback is on — every other enabled, usable provider in priority
    order. Providers with no API key (cloud) or no cached model (local) are
    skipped from the fallback chain."""
    cands: list[Candidate] = []
    seen: set[str] = set()

    pref = _parse_preferred(preferred_repo)
    if pref:
        cands.append(pref)
        seen.add(pref.id)

    if not fallback:
        return cands

    # Normalize the configured priority order, appending any ids it omits.
    known = _default_order()
    order = [o for o in app_settings.get_provider_priority() if o in known]
    order += [k for k in known if k not in order]

    for pid in order:
        if pid in seen:
            continue
        if not app_settings.get_provider_enabled(pid):
            continue
        if pid == "local":
            m = _local_default_model()
            if not m:
                continue
            cands.append(Candidate("local", "Local (MLX)", m, "local"))
        else:
            p = providers.PROVIDERS.get(pid)
            if not p or not providers.get_api_key(pid):
                continue
            m = _provider_default_model(pid)
            if not m:
                continue
            cands.append(Candidate(pid, p.name, m, "cloud"))
        seen.add(pid)
    return cands


# ───────────── error classification ─────────────

def classify(e: Exception) -> str:
    if isinstance(e, asyncio.TimeoutError):
        return "timeout"
    if isinstance(e, httpx.TimeoutException):
        return "timeout"
    if isinstance(e, httpx.ConnectError):
        return "connection"
    if isinstance(e, _EmptyResponse):
        return "empty"
    s = str(e).lower()
    if "429" in s or "rate limit" in s or "too many requests" in s:
        return "rate_limit"
    if any(x in s for x in ("500", "502", "503", "504", "overloaded", "unavailable")):
        return "server"
    if "not loaded" in s or "not downloaded" in s or "not cached" in s:
        return "model_unavailable"
    if "api key" in s or "unauthor" in s or "401" in s or "403" in s:
        return "no_key"
    if "refused" in s or "connection" in s:
        return "connection"
    return "error"


# Errors worth retrying on the SAME provider (transient); others → next provider.
_RETRYABLE = {"timeout", "server", "rate_limit"}


# ───────────── per-candidate streaming ─────────────

async def _local_stream(repo: str, messages: list[dict], params: dict) -> AsyncIterator[str]:
    """Bridge the sync, worker-thread MLX generator to an async stream. Loads
    the model on demand (raises RuntimeError if it isn't cached)."""
    await asyncio.to_thread(llm_engine.manager.ensure_loaded, repo)
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    def worker():
        try:
            for chunk in llm_engine.manager.stream_chat(
                repo, messages, params["temperature"], params["max_tokens"], params["top_p"],
            ):
                asyncio.run_coroutine_threadsafe(q.put(("c", chunk)), loop)
            asyncio.run_coroutine_threadsafe(q.put((_DONE, None)), loop)
        except Exception as e:  # surfaced to the consumer below
            asyncio.run_coroutine_threadsafe(q.put(("e", e)), loop)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        kind, payload = await q.get()
        if kind == "c":
            yield payload
        elif kind is _DONE:
            return
        else:
            raise payload


async def _stream_candidate(cand: Candidate, messages: list[dict], params: dict) -> AsyncIterator[str]:
    if cand.kind == "cloud":
        provider = providers.PROVIDERS[cand.id]
        _, model = providers.parse_repo(providers.repo_id(cand.id, cand.model))
        async for c in providers.stream_chat(
            provider, model, messages, params["temperature"], params["max_tokens"], params["top_p"],
        ):
            yield c
    else:
        async for c in _local_stream(cand.model, messages, params):
            yield c


async def _stream_with_timeout(cand: Candidate, messages: list[dict], params: dict, timeout: int) -> AsyncIterator[str]:
    """Apply a time-to-first-token timeout so a dead/overloaded provider is
    detected quickly; once tokens flow, stream freely."""
    agen = _stream_candidate(cand, messages, params)
    try:
        first = await asyncio.wait_for(agen.__anext__(), timeout=timeout)
    except StopAsyncIteration:
        return  # empty stream → caller raises _EmptyResponse
    yield first
    async for c in agen:
        yield c


def _log(cand: Candidate, etype: str, secs: float, attempt: int, chars: int, error: str = "") -> None:
    msg = (f"[router] attempt {attempt} · {cand.id}/{cand.model} · {etype} · "
           f"{secs:.1f}s · {chars} chars" + (f" · {error}" if error else ""))
    print(msg, file=sys.stderr, flush=True)


# ───────────── public API ─────────────

async def generate(
    messages: list[dict],
    preferred_repo: Optional[str],
    params: dict,
    *,
    uninterrupted: bool,
    timeout: int,
) -> AsyncIterator[dict]:
    cands = build_candidates(preferred_repo, fallback=uninterrupted)
    if not cands:
        yield {"type": "error", "detail": "No usable provider/model is configured."}
        return

    first_id = cands[0].id
    attempts = 0

    for cand in cands:
        retries = 0
        while True:
            if attempts >= GLOBAL_MAX_ATTEMPTS:
                yield {"type": "error", "detail": f"Gave up after {attempts} attempts across providers.", "exhausted": True}
                return
            attempts += 1
            t0 = time.time()
            chars = 0
            try:
                async for text in _stream_with_timeout(cand, messages, params, timeout):
                    if text:
                        chars += len(text)
                        yield {"type": "chunk", "text": text}
                if chars == 0:
                    raise _EmptyResponse()
                _log(cand, "ok", time.time() - t0, attempts, chars)
                yield {
                    "type": "done",
                    "provider_id": cand.id,
                    "provider": cand.name,
                    "model": cand.model,
                    "fallback": cand.id != first_id,
                }
                return
            except Exception as e:
                etype = classify(e)
                _log(cand, etype, time.time() - t0, attempts, chars, str(e)[:160])
                # Stream broke AFTER text already appeared — can't silently swap
                # providers (would duplicate / lose context), so stop and let the
                # UI offer a "Continue with fallback" (Phase 3).
                if chars > 0:
                    yield {"type": "interrupted", "provider": cand.name,
                           "detail": "Response was interrupted before it finished."}
                    return
                if not uninterrupted:
                    yield {"type": "error", "provider": cand.name, "detail": str(e)}
                    return
                if etype in _RETRYABLE and retries < PER_PROVIDER_RETRIES and attempts < GLOBAL_MAX_ATTEMPTS:
                    await asyncio.sleep(BACKOFF_SECONDS[min(retries, len(BACKOFF_SECONDS) - 1)])
                    retries += 1
                    continue
                break  # non-retryable or out of retries → next candidate

    yield {"type": "error", "detail": "All available providers failed.", "exhausted": True}
