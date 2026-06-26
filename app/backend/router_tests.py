"""
Test matrix for the Uninterrupted Mode router (router.py).

Self-contained — provider streams are SIMULATED (no real network / MLX), so it
runs fast and offline. Provider availability, priority and enabled-state are
controlled per scenario.

Run from the `app/` directory:

    ../conda_env/bin/python -m backend.router_tests

Exits non-zero if any scenario fails.

Covers the spec's matrix:
  - provider succeeds first try
  - first provider offline, second succeeds
  - rate-limit fallback (with same-provider retries)
  - timeout fallback
  - all providers fail
  - empty response → fallback
  - stream fails before text → fallback
  - stream fails after partial text → interrupted (no silent swap)
  - disabled providers are skipped
  - missing-API-key providers are skipped
  - global attempt cap is respected
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from . import providers, router, settings

_TESTS = []


def _test(fn):
    _TESTS.append(fn)
    return fn


# ───────────── harness ─────────────

def _setup(*, keys=(), priority=None, disabled=()):
    """Fresh, isolated settings + patched provider availability."""
    settings._PATH = Path("/tmp/cs_router_tests_settings.json")
    settings._loaded = False
    settings._cache = {}
    if priority:
        settings.set_provider_priority(priority)
    for pid in disabled:
        settings.set_provider_enabled(pid, False)
    keyset = set(keys)
    providers.get_api_key = lambda key, _k=keyset: ("k" if key in _k else None)
    router._local_default_model = lambda: "fake/local"
    router.BACKOFF_SECONDS = [0, 0, 0]  # no real sleeping in tests


def _streamer(behaviors, calls):
    """Returns a fake `_stream_with_timeout`. `behaviors` maps a candidate id to
    a tuple describing what its stream does. Unlisted ids default to a
    connection error."""
    async def fake(cand, messages, params, timeout):
        calls.append(cand.id)
        b = behaviors.get(cand.id, ("connection",))
        kind = b[0]
        if kind == "ok":
            for t in b[1]:
                yield t
            return
        if kind == "text_then_fail":
            for t in b[1]:
                yield t
            raise RuntimeError(b[2])
        if kind == "empty":
            return                       # completes with no text
        if kind == "timeout":
            raise asyncio.TimeoutError()
        if kind == "rate":
            raise RuntimeError("HTTP 429 too many requests")
        if kind == "server":
            raise RuntimeError("HTTP 503 overloaded")
        # default: connection refused
        raise httpx.ConnectError("connection refused")
    return fake


async def _gen(preferred, exclude=None):
    text, events = "", []
    async for ev in router.generate(
        [{"role": "user", "content": "hi"}], preferred,
        {"temperature": 0.7, "max_tokens": 16, "top_p": 1.0},
        uninterrupted=True, timeout=30, exclude_ids=exclude,
    ):
        if ev["type"] == "chunk":
            text += ev["text"]
        else:
            events.append(ev)
    return text, (events[-1] if events else None)


# ───────────── scenarios ─────────────

@_test
async def succeeds_first_try():
    _setup(priority=["local", "openrouter"])
    calls = []
    router._stream_with_timeout = _streamer({"local": ("ok", ["hello"])}, calls)
    text, e = await _gen("fake/local")
    return (e and e["type"] == "done" and e["provider_id"] == "local"
            and not e["fallback"] and calls == ["local"]), f"{calls} {e}"


@_test
async def offline_then_next_succeeds():
    _setup(keys=["openrouter"], priority=["local", "openrouter"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"local": ("connection",), "openrouter": ("ok", ["hi"])}, calls)
    text, e = await _gen("fake/local")
    return (e["type"] == "done" and e["provider_id"] == "openrouter"
            and e["fallback"] and calls == ["local", "openrouter"]), f"{calls} {e}"


@_test
async def rate_limit_retries_then_fallback():
    _setup(keys=["openrouter"], priority=["openrouter", "local"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"openrouter": ("rate",), "local": ("ok", ["ok"])}, calls)
    text, e = await _gen("provider:openrouter:m")
    # 429 is retryable → openrouter tried 1 + 2 retries = 3, then local
    return (e["provider_id"] == "local" and calls.count("openrouter") == 3
            and calls[-1] == "local"), f"{calls} {e}"


@_test
async def timeout_retries_then_fallback():
    _setup(keys=["openrouter"], priority=["openrouter", "local"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"openrouter": ("timeout",), "local": ("ok", ["ok"])}, calls)
    text, e = await _gen("provider:openrouter:m")
    return (e["provider_id"] == "local" and calls.count("openrouter") == 3), f"{calls} {e}"


@_test
async def all_providers_fail():
    _setup(keys=["openrouter"], priority=["local", "openrouter"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"local": ("connection",), "openrouter": ("connection",)}, calls)
    text, e = await _gen("fake/local")
    return (e["type"] == "error" and e.get("exhausted")
            and calls == ["local", "openrouter"]), f"{calls} {e}"


@_test
async def empty_response_falls_back():
    _setup(keys=["openrouter"], priority=["openrouter", "local"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"openrouter": ("empty",), "local": ("ok", ["recovered"])}, calls)
    text, e = await _gen("provider:openrouter:m")
    return (e["provider_id"] == "local" and "recovered" in text), f"{calls} {e}"


@_test
async def break_before_text_falls_back():
    _setup(keys=["openrouter"], priority=["openrouter", "local"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"openrouter": ("connection",), "local": ("ok", ["fresh"])}, calls)
    text, e = await _gen("provider:openrouter:m")
    return (e["provider_id"] == "local" and "fresh" in text), f"{calls} {e}"


@_test
async def break_after_text_interrupts_without_swap():
    _setup(keys=["openrouter"], priority=["openrouter", "local"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"openrouter": ("text_then_fail", ["partial "], "HTTP 503"),
         "local": ("ok", ["X"])}, calls)
    text, e = await _gen("provider:openrouter:m")
    return (e["type"] == "interrupted" and e["provider_id"] == "openrouter"
            and "partial" in text and "local" not in calls), f"{calls} {e}"


@_test
async def disabled_providers_skipped():
    _setup(keys=["openrouter", "groq"], priority=["openrouter", "local", "groq"], disabled=["local"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"openrouter": ("connection",), "groq": ("ok", ["g"])}, calls)
    text, e = await _gen("provider:openrouter:m")
    return (e["provider_id"] == "groq" and "local" not in calls), f"{calls} {e}"


@_test
async def missing_key_providers_skipped():
    _setup(keys=["groq"], priority=["openrouter", "nvidia", "groq", "local"])
    calls = []
    router._stream_with_timeout = _streamer(
        {"openrouter": ("connection",), "groq": ("ok", ["g"])}, calls)
    text, e = await _gen("provider:openrouter:m")
    # nvidia has no key → never attempted
    return (e["provider_id"] == "groq" and "nvidia" not in calls), f"{calls} {e}"


@_test
async def global_attempt_cap_respected():
    _setup(keys=["openrouter", "groq", "gemini"],
           priority=["openrouter", "groq", "gemini", "local"])
    calls = []
    behaviors = {pid: ("rate",) for pid in ("openrouter", "groq", "gemini", "local")}
    router._stream_with_timeout = _streamer(behaviors, calls)
    text, e = await _gen("provider:openrouter:m")
    return (e["type"] == "error" and len(calls) <= router.GLOBAL_MAX_ATTEMPTS), \
        f"{len(calls)} attempts {e}"


# ───────────── runner ─────────────

async def run_all() -> int:
    passed = failed = 0
    for fn in _TESTS:
        try:
            ok, detail = await fn()
        except Exception as e:  # a raised exception is a failure
            ok, detail = False, f"raised {type(e).__name__}: {e}"
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {fn.__name__}" + ("" if ok else f"   → {detail}"))
        passed += ok
        failed += (not ok)
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(run_all()))
