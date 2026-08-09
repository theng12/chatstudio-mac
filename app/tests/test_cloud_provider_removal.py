import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import main


ROOT = Path(__file__).resolve().parents[2]


def test_cloud_provider_and_fallback_routes_are_gone():
    paths = {route.path for route in main.app.routes}
    assert "/api/providers" not in paths
    assert "/api/router/providers" not in paths
    assert "/api/router/health" not in paths


@pytest.mark.parametrize("openai_compatible", [False, True])
def test_stale_cloud_model_ids_fail_clearly(openai_compatible):
    if openai_compatible:
        body = main.OpenAIChatCompletionsBody(
            model="provider:openrouter:stale-model",
            messages=[main.ChatMessage(role="user", content="hello")],
        )
        call = main.openai_chat_completions(body)
    else:
        body = main.ChatCompletionsBody(
            repo="provider:openrouter:stale-model",
            messages=[main.ChatMessage(role="user", content="hello")],
        )
        call = main.chat_completions(body)

    with pytest.raises(HTTPException, match="Cloud providers are no longer supported") as error:
        asyncio.run(call)
    assert error.value.status_code == 400


def test_settings_api_exposes_only_the_hugging_face_credential(monkeypatch):
    monkeypatch.setattr(main.app_settings, "get_hf_token", lambda: None)
    assert main.get_settings() == {"hf_token_set": False, "hf_token_masked": ""}


def test_cloud_controls_and_credentials_are_absent_from_product_files():
    html = (ROOT / "app/frontend/index.html").read_text()
    javascript = (ROOT / "app/frontend/app.js").read_text()
    environment = (ROOT / "ENVIRONMENT").read_text()

    assert "Cloud providers" not in html
    assert "Uninterrupted Mode" not in html
    assert "/api/providers" not in javascript
    assert "/api/router" not in javascript
    assert "CHATSTUDIO_OPENROUTER_API_KEY" not in environment


def test_engine_warning_waits_for_diagnostics():
    html = (ROOT / "app/frontend/index.html").read_text()
    javascript = (ROOT / "app/frontend/app.js").read_text()

    assert 'diag: { checked: false, available: false' in javascript
    assert 'x-if="diag.checked && !diag.available"' in html
