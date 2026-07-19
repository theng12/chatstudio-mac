"""Chat Studio's fixed, non-user-editable updater identity."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .auto_update import AutoUpdater


ROOT = Path(__file__).resolve().parents[2]
SPEC = {
    "root": str(ROOT),
    "title": "Chat Studio KH",
    "slug": "chatstudio",
    "expected_remote": "https://github.com/theng12/chatstudio-mac.git",
    "branch": "main",
    "port": 47871,
    "server_label": "com.kh.chatstudio.server",
    "watchdog_label": "com.kh.chatstudio.watchdog",
    "default_hour": 3,
    "default_weekday": 6,
    "verify_module": "backend.main",
    "allow_build_suffix": False,
}


def create_updater(readiness: Optional[Callable[[], list[str]]] = None, **kwargs) -> AutoUpdater:
    return AutoUpdater(SPEC, readiness=readiness, **kwargs)
