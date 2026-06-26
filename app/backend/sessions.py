"""
Persistent chat sessions (history) for the web chat.

Stored server-side in `sessions.json` (gitignored) so history survives browser
cache clears and is visible from any device pointed at this server. Each
session keeps the full message list, so reopening one restores the whole
conversation — and continuing it re-sends that context to the model.

Shape on disk: { "<id>": {id, title, model, pinned, created, updated, messages} }
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parent / "sessions.json"
_LOCK = threading.Lock()


def _load() -> dict:
    try:
        if _PATH.exists():
            d = json.loads(_PATH.read_text())
            if isinstance(d, dict):
                return d
    except Exception:
        pass
    return {}


def _save(d: dict) -> None:
    tmp = _PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, _PATH)


def _derive_title(messages: list) -> str:
    for m in messages:
        if m.get("role") == "user" and (m.get("content") or "").strip():
            t = " ".join((m["content"] or "").split())
            return t[:60] + ("…" if len(t) > 60 else "")
    return "New chat"


def _meta(s: dict) -> dict:
    return {
        "id": s["id"],
        "title": s.get("title") or "New chat",
        "model": s.get("model"),
        "pinned": bool(s.get("pinned")),
        "created": s.get("created"),
        "updated": s.get("updated"),
        "count": len(s.get("messages", [])),
    }


def upsert(session: dict) -> dict:
    """Create or update a session; returns its metadata (incl. the assigned id)."""
    with _LOCK:
        d = _load()
        sid = session.get("id") or uuid.uuid4().hex[:12]
        existing = d.get(sid, {})
        messages = session.get("messages")
        if messages is None:
            messages = existing.get("messages", [])
        now = time.time()
        s = {
            "id": sid,
            "title": session.get("title") or existing.get("title") or _derive_title(messages),
            "model": session.get("model", existing.get("model")),
            "pinned": bool(session.get("pinned", existing.get("pinned", False))),
            "created": existing.get("created", now),
            "updated": now,
            "messages": messages,
        }
        d[sid] = s
        _save(d)
        return _meta(s)


def get(sid: str) -> Optional[dict]:
    with _LOCK:
        return _load().get(sid)


def delete(sid: str) -> bool:
    with _LOCK:
        d = _load()
        if sid in d:
            del d[sid]
            _save(d)
            return True
        return False


def set_pinned(sid: str, pinned: bool) -> bool:
    with _LOCK:
        d = _load()
        if sid not in d:
            return False
        d[sid]["pinned"] = bool(pinned)
        _save(d)
        return True


def rename(sid: str, title: str) -> bool:
    with _LOCK:
        d = _load()
        if sid not in d:
            return False
        d[sid]["title"] = (title or "").strip() or d[sid].get("title") or "New chat"
        _save(d)
        return True


def list_meta(q: str = "") -> list[dict]:
    """Session metadata, pinned first then most-recent. `q` matches the title or
    any message content (case-insensitive)."""
    with _LOCK:
        items = list(_load().values())
    ql = (q or "").strip().lower()
    if ql:
        def match(s: dict) -> bool:
            if ql in (s.get("title", "") or "").lower():
                return True
            for m in s.get("messages", []):
                if ql in (m.get("content", "") or "").lower():
                    return True
            return False
        items = [s for s in items if match(s)]
    items.sort(key=lambda s: (not s.get("pinned"), -(s.get("updated") or 0)))
    return [_meta(s) for s in items]
