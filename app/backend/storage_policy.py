"""Fleet storage-policy contract for Chat Studio.

Chat Studio produces no disposable media assets. Model weights and server-side
chat history are user data and deliberately excluded. Persisting the common
policy still lets Studio Hub show one consistent fleet view without inventing a
dangerous cleanup target.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import HTTPException

SETTINGS_FILE = Path(__file__).resolve().parent / "storage_policy.json"
DEFAULTS = {"enabled": True, "retention_days": 3, "max_gb": 80.0}


def read() -> dict:
    try:
        value = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    return {**DEFAULTS, **(value if isinstance(value, dict) else {})}


def save(enabled: object, retention_days: object, max_gb: object) -> dict:
    if not isinstance(enabled, bool):
        raise HTTPException(400, "enabled must be true or false")
    try:
        days, maximum = int(retention_days), float(max_gb)
    except (TypeError, ValueError):
        raise HTTPException(400, "retention_days and max_gb must be numbers")
    if not 1 <= days <= 3650:
        raise HTTPException(400, "retention_days must be between 1 and 3650")
    if not 1 <= maximum <= 1000:
        raise HTTPException(400, "max_gb must be between 1 and 1000")
    value = {"enabled": enabled, "retention_days": days, "max_gb": maximum}
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    partial = SETTINGS_FILE.with_suffix(".json.tmp")
    partial.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(partial, SETTINGS_FILE)
    return value


def status() -> dict:
    policy = read()
    return {
        **policy, "supported": False, "used_bytes": 0, "count": 0,
        "max_bytes": round(float(policy["max_gb"]) * 1024 ** 3),
        "over_limit": False,
        "scope": "no disposable media; chat history and models are protected",
    }


def cleanup() -> dict:
    return {**status(), "deleted": 0, "freed_bytes": 0, "used_before_bytes": 0}
