from fastapi.testclient import TestClient

from backend import storage_policy
from backend.main import FLEET_TOKEN, app


def test_policy_api_is_consistent_but_has_no_disposable_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_policy, "SETTINGS_FILE", tmp_path / "policy.json")
    history = tmp_path / "sessions.json"
    history.write_text('{"private":"conversation"}')
    client = TestClient(app, headers={"X-Studio-Token": FLEET_TOKEN})

    saved = client.put("/api/storage-policy", json={
        "enabled": True, "retention_days": 3, "max_gb": 80,
    })
    cleaned = client.post("/api/storage-policy/cleanup", json={"target_bytes": 0})

    assert saved.status_code == 200
    assert saved.json()["supported"] is False
    assert cleaned.json()["deleted"] == 0
    assert history.exists()
    assert "chat history" in cleaned.json()["scope"]
