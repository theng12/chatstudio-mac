from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import restart_health
from backend.main import app


def _write_events(path: Path, stamps: list[str]) -> None:
    path.write_text(
        "".join(
            f"[watchdog] {stamp} no /api/health on :47871 — restarting com.kh.chatstudio.server\n"
            for stamp in stamps
        ),
        encoding="utf-8",
    )


def test_restart_rate_is_healthy_without_recent_restarts(tmp_path: Path) -> None:
    log = tmp_path / "watchdog.log"
    _write_events(log, ["2026-07-01 10:00:00"])

    result = restart_health.snapshot(
        log, now=datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
    )

    assert result["status"] == "healthy"
    assert result["alert"] is False
    assert result["restarts_24h"] == 0
    assert result["last_restart_at"] == "2026-07-01T10:00:00+00:00"


def test_restart_rate_warns_and_escalates_from_bounded_log_evidence(tmp_path: Path) -> None:
    log = tmp_path / "watchdog.log"
    warning_events = [
        "2026-07-23 08:10:00",
        "2026-07-23 08:20:00",
        "2026-07-23 08:30:00",
    ]
    _write_events(log, warning_events)
    now = datetime(2026, 7, 23, 9, 0, tzinfo=timezone.utc)

    warning = restart_health.snapshot(log, now=now)
    assert warning["status"] == "warning"
    assert warning["alert"] is True
    assert warning["restarts_1h"] == 3

    _write_events(log, warning_events + [
        "2026-07-23 08:35:00",
        "2026-07-23 08:40:00",
        "2026-07-23 08:45:00",
    ])
    critical = restart_health.snapshot(log, now=now)
    assert critical["status"] == "critical"
    assert critical["restarts_1h"] == 6


def test_missing_watchdog_log_never_makes_the_app_unhealthy(tmp_path: Path) -> None:
    result = restart_health.snapshot(tmp_path / "missing.log")

    assert result == {
        "available": False,
        "status": "unavailable",
        "alert": False,
        "restarts_1h": 0,
        "restarts_24h": 0,
        "restarts_7d": 0,
        "last_restart_at": None,
    }


def test_health_exposes_read_only_restart_rate_signal() -> None:
    evidence = {
        "available": True,
        "status": "warning",
        "alert": True,
        "restarts_1h": 3,
        "restarts_24h": 4,
        "restarts_7d": 7,
        "last_restart_at": "2026-07-23T08:30:00+07:00",
    }
    with patch.object(restart_health, "snapshot", return_value=evidence):
        response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["restart_rate"] == evidence
