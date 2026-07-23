import json

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


def test_legacy_three_day_policy_migrates_once_to_thirty_days(
        tmp_path, monkeypatch):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({
        "enabled": True, "retention_days": 3, "max_gb": 80,
    }))
    monkeypatch.setattr(storage_policy, "SETTINGS_FILE", policy_file)

    assert storage_policy.read()["retention_days"] == 30
    migrated = json.loads(policy_file.read_text())
    assert migrated["retention_days"] == 30
    assert migrated["policy_version"] == storage_policy.POLICY_VERSION

    storage_policy.save(True, 3, 80)
    assert storage_policy.read()["retention_days"] == 3
