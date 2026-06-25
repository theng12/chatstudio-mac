"""
Cloud LLM provider support for Chat Studio (Mac).

Defines providers (OpenRouter, NVIDIA NIM) that expose OpenAI-compatible
chat-completions APIs. Each provider has:
  - An OpenAI-compatible base URL
  - An env-or-settings API key
  - A curated list of free models (id + display label + notes)

The frontend asks for these models via GET /api/providers, and the chat
endpoint routes to the cloud API when the selected `repo` has the
synthetic `provider:<name>:<model_id>` form.

Streaming uses httpx so we can pipe the upstream SSE/ndjson chunks
straight into the app's own StreamingResponse, with no buffering.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import httpx

from . import settings as app_settings


@dataclass(frozen=True)
class CloudModel:
    id: str               # the model id the upstream API expects
    label: str            # human-friendly name for the UI
    notes: str = ""       # short tagline (context window, strengths, etc.)


@dataclass(frozen=True)
class Provider:
    key: str              # short slug used in the synthetic repo id
    name: str             # display name
    base_url: str         # OpenAI-compatible base
    models: tuple[CloudModel, ...]
    env_var: str          # env var name (CHATSTUDIO_<KEY>_API_KEY) for override
    docs_url: str = ""


OPENROUTER = Provider(
    key="openrouter",
    name="OpenRouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="CHATSTUDIO_OPENROUTER_API_KEY",
    docs_url="https://openrouter.ai/keys",
    models=(
        CloudModel(
            "meta-llama/llama-3.3-70b-instruct:free",
            "Llama 3.3 70B Instruct (free)",
            "Strong generalist · 128K context",
        ),
        CloudModel(
            "meta-llama/llama-3.1-8b-instruct:free",
            "Llama 3.1 8B Instruct (free)",
            "Fast small model · good for quick replies",
        ),
        CloudModel(
            "google/gemma-3-27b-it:free",
            "Gemma 3 27B IT (free)",
            "Google's 27B instruction-tuned model",
        ),
        CloudModel(
            "qwen/qwen-2.5-72b-instruct:free",
            "Qwen 2.5 72B Instruct (free)",
            "Strong coding + multilingual",
        ),
        CloudModel(
            "mistralai/mistral-small-3.2-24b-instruct:free",
            "Mistral Small 3.2 24B (free)",
            "Mistral's 24B instruction-tuned",
        ),
        CloudModel(
            "deepseek/deepseek-chat-v3.1:free",
            "DeepSeek V3.1 Chat (free)",
            "DeepSeek's latest general chat model",
        ),
        CloudModel(
            "nvidia/llama-3.1-nemotron-70b-instruct:free",
            "Llama 3.1 Nemotron 70B (free)",
            "NVIDIA-tuned Llama · strong reasoning",
        ),
    ),
)


NVIDIA = Provider(
    key="nvidia",
    name="NVIDIA NIM",
    base_url="https://integrate.api.nvidia.com/v1",
    env_var="CHATSTUDIO_NVIDIA_API_KEY",
    docs_url="https://build.nvidia.com/explore/discover",
    models=(
        CloudModel(
            "meta/llama-3.1-70b-instruct",
            "Llama 3.1 70B Instruct",
            "NVIDIA-hosted · strong generalist",
        ),
        CloudModel(
            "meta/llama-3.1-8b-instruct",
            "Llama 3.1 8B Instruct",
            "Fast small model",
        ),
        CloudModel(
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "Nemotron 70B Instruct",
            "NVIDIA's reasoning-tuned 70B",
        ),
        CloudModel(
            "nvidia/llama-3.3-nemotron-super-49b-v1",
            "Nemotron Super 49B v1",
            "Strong reasoning · larger context",
        ),
        CloudModel(
            "mistralai/mistral-large-2-instruct",
            "Mistral Large 2",
            "Mistral's flagship 123B",
        ),
        CloudModel(
            "google/gemma-3-27b-it",
            "Gemma 3 27B IT",
            "Google's 27B instruction-tuned",
        ),
        CloudModel(
            "qwen/qwen2.5-coder-32b-instruct",
            "Qwen 2.5 Coder 32B",
            "Code-focused Qwen model",
        ),
    ),
)


PROVIDERS: dict[str, Provider] = {p.key: p for p in (OPENROUTER, NVIDIA)}


def get_api_key(key: str) -> Optional[str]:
    """Env var wins, then settings.json. Returns the trimmed key or None."""
    p = PROVIDERS.get(key)
    if not p:
        return None
    env = (os.environ.get(p.env_var) or "").strip()
    if env:
        return env
    stored = (app_settings.get_provider_key(key) or "").strip()
    return stored or None


def repo_id(key: str, model_id: str) -> str:
    """Synthetic repo id used in the existing /api/chat/load and
    /api/chat/completions flow so the cloud models slot in without a new
    code path on the frontend."""
    return f"provider:{key}:{model_id}"


def parse_repo(repo: str) -> Optional[tuple[Provider, CloudModel]]:
    """Return (provider, model) if `repo` is a synthetic cloud id, else None."""
    if not repo or not repo.startswith("provider:"):
        return None
    parts = repo.split(":", 2)
    if len(parts) != 3:
        return None
    _, key, model_id = parts
    p = PROVIDERS.get(key)
    if not p:
        return None
    for m in p.models:
        if m.id == model_id:
            return p, m
    # Unknown model id on a known provider — still let it through so we
    # don't break if the provider adds a model before we update the list.
    return p, CloudModel(id=model_id, label=model_id)


def public_view() -> list[dict]:
    """Shape returned by GET /api/providers — never includes raw API keys."""
    out = []
    for p in PROVIDERS.values():
        token = get_api_key(p.key)
        out.append({
            "key": p.key,
            "name": p.name,
            "base_url": p.base_url,
            "docs_url": p.docs_url,
            "key_set": bool(token),
            "key_masked": _mask(token) if token else "",
            "models": [
                {"id": m.id, "label": m.label, "notes": m.notes, "repo": repo_id(p.key, m.id)}
                for m in p.models
            ],
        })
    return out


def _mask(token: str) -> str:
    if len(token) >= 10:
        return token[:3] + "…" + token[-4:]
    return "•" * len(token)


async def stream_chat(
    provider: Provider,
    model: CloudModel,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    top_p: float,
) -> AsyncIterator[str]:
    """Yields raw text deltas from the upstream OpenAI-compatible
    /chat/completions?stream=true endpoint. Caller is responsible for
    forwarding these as the app's own streaming response."""
    api_key = get_api_key(provider.key)
    if not api_key:
        raise RuntimeError(
            f"{provider.name} API key not set. Add it in Settings → Cloud providers."
        )
    url = f"{provider.base_url}/chat/completions"
    payload = {
        "model": model.id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as r:
            if r.status_code >= 400:
                # Drain the body for the error text, then raise
                body = (await r.aread()).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"{provider.name} returned HTTP {r.status_code}: {body[:300]}"
                )
            async for line in r.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        import json
                        obj = json.loads(data)
                    except Exception:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    chunk = delta.get("content")
                    if chunk:
                        yield chunk
