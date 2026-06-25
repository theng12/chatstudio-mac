"""
Persistent app settings.

Stored as JSON at `app/backend/settings.json` (gitignored). Currently holds
the Hugging Face token; structured as a dict so we can add more keys later
without rev-bumping the file format.

The token is read/written via the get_hf_token / set_hf_token helpers; the
download manager falls back to this token whenever the user doesn't pass an
explicit per-download token. Atomic writes (tmp → rename) so a crash mid-save
can't corrupt the file.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional


_PATH = Path(__file__).resolve().parent / "settings.json"
_LOCK = threading.Lock()

DEFAULTS: dict[str, Any] = {
    "hf_token": "",
    "provider_keys": {},          # {"openrouter": "...", "nvidia": "..."}
    "provider_paid_enabled": {},  # {"openrouter": true} — opt-in to paid models
    # ── Uninterrupted Mode (auto-fallback router) ──
    "uninterrupted_mode": False,
    "request_timeout": 60,        # seconds; time-to-first-token before fallback
    "provider_priority": [],      # ordered ids incl. "local"; [] = default order
    "provider_enabled": {},       # {id: bool}; default True
}

_cache: dict[str, Any] = {}
_loaded = False


def _load_if_needed() -> None:
    global _cache, _loaded
    if _loaded:
        return
    try:
        if _PATH.exists():
            data = json.loads(_PATH.read_text())
            if isinstance(data, dict):
                _cache = {**DEFAULTS, **data}
            else:
                _cache = dict(DEFAULTS)
        else:
            _cache = dict(DEFAULTS)
    except Exception:
        _cache = dict(DEFAULTS)
    _loaded = True


def get(key: str) -> Any:
    with _LOCK:
        _load_if_needed()
        return _cache.get(key, DEFAULTS.get(key))


def set_value(key: str, value: Any) -> None:
    with _LOCK:
        _load_if_needed()
        _cache[key] = value
        tmp = _PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_cache, indent=2))
        os.replace(tmp, _PATH)


def get_hf_token() -> Optional[str]:
    # An explicit env override wins, as documented in the ENVIRONMENT file
    # (CHATSTUDIO_HF_TOKEN "Overrides the UI's saved token"). HF_TOKEN is also
    # honored so a standard Hugging Face env var just works.
    env = (os.environ.get("CHATSTUDIO_HF_TOKEN") or os.environ.get("HF_TOKEN") or "").strip()
    if env:
        return env
    token = get("hf_token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def set_hf_token(token: Optional[str]) -> None:
    set_value("hf_token", (token or "").strip())


def get_provider_key(name: str) -> Optional[str]:
    keys = get("provider_keys")
    if not isinstance(keys, dict):
        return None
    val = keys.get(name)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def set_provider_key(name: str, token: Optional[str]) -> None:
    keys = dict(get("provider_keys") or {})
    if token:
        keys[name] = token.strip()
    else:
        keys.pop(name, None)
    set_value("provider_keys", keys)


def get_provider_paid(name: str) -> bool:
    d = get("provider_paid_enabled")
    return bool(d.get(name)) if isinstance(d, dict) else False


def set_provider_paid(name: str, enabled: bool) -> None:
    d = dict(get("provider_paid_enabled") or {})
    d[name] = bool(enabled)
    set_value("provider_paid_enabled", d)


# ── Uninterrupted Mode ──

def get_uninterrupted() -> bool:
    return bool(get("uninterrupted_mode"))


def set_uninterrupted(enabled: bool) -> None:
    set_value("uninterrupted_mode", bool(enabled))


def get_request_timeout() -> int:
    t = get("request_timeout")
    try:
        t = int(t)
        return t if t >= 5 else 60
    except (TypeError, ValueError):
        return 60


def set_request_timeout(seconds: int) -> None:
    try:
        set_value("request_timeout", max(5, int(seconds)))
    except (TypeError, ValueError):
        pass


def get_provider_priority() -> list:
    p = get("provider_priority")
    return list(p) if isinstance(p, list) else []


def set_provider_priority(order: list) -> None:
    set_value("provider_priority", [str(x) for x in (order or [])])


def get_provider_enabled(name: str) -> bool:
    d = get("provider_enabled")
    return bool(d.get(name, True)) if isinstance(d, dict) else True


def set_provider_enabled(name: str, enabled: bool) -> None:
    d = dict(get("provider_enabled") or {})
    d[name] = bool(enabled)
    set_value("provider_enabled", d)


def serialize_public() -> dict:
    """
    Caller-safe view: never includes the raw token. Returns a masked preview
    (first 3 + last 4 chars) so users can confirm the right token is saved.
    """
    token = get_hf_token()
    base = {
        "uninterrupted_mode": get_uninterrupted(),
        "request_timeout": get_request_timeout(),
    }
    if not token:
        return {**base, "hf_token_set": False, "hf_token_masked": ""}
    masked = token[:3] + "…" + token[-4:] if len(token) >= 10 else "•" * len(token)
    return {**base, "hf_token_set": True, "hf_token_masked": masked}
