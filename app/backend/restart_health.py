"""Bounded, read-only watchdog restart-rate telemetry for fleet health."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCHDOG_LOG = ROOT / "logs" / "service" / "watchdog.log"
MAX_LOG_BYTES = 1_000_000
_RESTART_RE = re.compile(
    r"^\[watchdog\]\s+(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+.*\brestarting\b"
)


def _recent_log_text(path: Path) -> tuple[str, bool]:
    """Read at most the newest MAX_LOG_BYTES so health checks stay inexpensive."""
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        truncated = size > MAX_LOG_BYTES
        handle.seek(max(0, size - MAX_LOG_BYTES))
        data = handle.read(MAX_LOG_BYTES)
    return data.decode("utf-8", errors="replace"), truncated


def snapshot(log_path: Path = WATCHDOG_LOG, *, now: datetime | None = None) -> dict:
    """Return restart-rate evidence without changing service or dispatch state."""
    observed_at = now or datetime.now().astimezone()
    if observed_at.tzinfo is None:
        observed_at = observed_at.astimezone()

    try:
        text, truncated = _recent_log_text(log_path)
    except OSError:
        return {
            "available": False,
            "status": "unavailable",
            "alert": False,
            "restarts_1h": 0,
            "restarts_24h": 0,
            "restarts_7d": 0,
            "last_restart_at": None,
        }

    events: list[datetime] = []
    for line in text.splitlines():
        match = _RESTART_RE.match(line)
        if not match:
            continue
        try:
            event = datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        events.append(event.replace(tzinfo=observed_at.tzinfo))

    one_hour = sum(observed_at - timedelta(hours=1) <= event <= observed_at for event in events)
    one_day = sum(observed_at - timedelta(days=1) <= event <= observed_at for event in events)
    seven_days = sum(observed_at - timedelta(days=7) <= event <= observed_at for event in events)
    if one_hour >= 6 or one_day >= 12 or seven_days >= 30:
        status = "critical"
    elif one_hour >= 3 or one_day >= 4 or seven_days >= 10:
        status = "warning"
    else:
        status = "healthy"

    return {
        "available": True,
        "status": status,
        "alert": status in {"warning", "critical"},
        "restarts_1h": one_hour,
        "restarts_24h": one_day,
        "restarts_7d": seven_days,
        "last_restart_at": events[-1].isoformat() if events else None,
        "events_in_sample": len(events),
        "sample_truncated": truncated,
        "thresholds": {
            "warning": {"restarts_1h": 3, "restarts_24h": 4, "restarts_7d": 10},
            "critical": {"restarts_1h": 6, "restarts_24h": 12, "restarts_7d": 30},
        },
    }
