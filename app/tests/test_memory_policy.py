from pathlib import Path

from fastapi.testclient import TestClient

from backend import memory_policy
from backend.main import FLEET_TOKEN, app
from backend.process_title import PROCESS_TITLE


class Manager:
    def __init__(self, repo="mlx-community/test", idle=0.0, busy=False):
        self.repo = repo
        self.idle = idle
        self.busy = busy
        self.releases = 0

    def loaded_repo(self):
        return self.repo

    def idle_seconds(self):
        return self.idle if self.repo else None

    def is_busy(self):
        return self.busy

    def release_memory(self, reason="manual"):
        self.releases += 1
        repo, self.repo = self.repo, None
        return {"released": bool(repo), "repo": repo, "actions": ["test cache cleared"]}


def _reset(monkeypatch, tmp_path, manager=None, active=False):
    monkeypatch.setattr(memory_policy, "SETTINGS_FILE", tmp_path / "memory_policy.json")
    monkeypatch.setattr(memory_policy, "_MANAGER", manager or Manager())
    monkeypatch.setattr(memory_policy, "_ACTIVE_CHECK", lambda: active)
    monkeypatch.setattr(memory_policy, "_LAST_RELEASE_AT", None)
    monkeypatch.setattr(memory_policy, "_LAST_RELEASE_REASON", None)
    monkeypatch.setattr(memory_policy, "_LAST_RELEASE_DETAILS", None)
    monkeypatch.setattr(memory_policy, "_LAST_ERROR", None)
    monkeypatch.setattr(memory_policy, "_RELEASE_COUNT", 0)
    monkeypatch.setattr(memory_policy, "_RELEASING", False)


def test_default_preserves_loaded_model_for_performance(tmp_path, monkeypatch):
    manager = Manager(idle=99_999)
    _reset(monkeypatch, tmp_path, manager)
    assert memory_policy.status()["mode"] == "performance"
    assert memory_policy.run_due_release(now=100_000) is None
    assert manager.releases == 0


def test_balanced_and_memory_saver_deadlines(tmp_path, monkeypatch):
    manager = Manager(idle=599)
    _reset(monkeypatch, tmp_path, manager)
    memory_policy.save("balanced")
    assert memory_policy.run_due_release(now=700) is None
    manager.idle = 600
    released = memory_policy.run_due_release(now=701)
    assert released["last_release_reason"] == "automatic:balanced"
    assert released["busy"] is False
    assert manager.releases == 1


def test_active_chat_blocks_manual_release(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path, Manager(), active=True)
    client = TestClient(app, headers={"X-Studio-Token": FLEET_TOKEN})
    response = client.post("/api/memory/release")
    assert response.status_code == 409


def test_memory_api_frontend_and_process_title(tmp_path, monkeypatch):
    _reset(monkeypatch, tmp_path)
    client = TestClient(app, headers={"X-Studio-Token": FLEET_TOKEN})
    saved = client.put("/api/memory-policy", json={"mode": "memory_saver"})
    assert saved.status_code == 200
    assert saved.json()["idle_seconds"] == 120
    released = client.post("/api/memory/release")
    assert released.status_code == 200
    assert released.json()["last_release_details"]["released"] is True

    root = Path(__file__).parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (root / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "Release Memory / Unload Model" in html
    assert "Performance · default" in html
    assert 'fetch(`${this.apiBase}/api/memory-policy`' in script
    assert 'fetch(`${this.apiBase}/api/memory/release`' in script
    assert PROCESS_TITLE == "Chat Studio Mac"
