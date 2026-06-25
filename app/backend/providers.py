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
    free: bool = True      # False = paid; hidden until the provider's paid toggle is on


@dataclass(frozen=True)
class Provider:
    key: str              # short slug used in the synthetic repo id
    name: str             # display name
    base_url: str         # OpenAI-compatible base
    models: tuple[CloudModel, ...]
    env_var: str          # env var name (CHATSTUDIO_<KEY>_API_KEY) for override
    docs_url: str = ""
    reuse_hf_token: bool = False   # fall back to the saved Hugging Face token (HF Router)


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
        # ── Paid (hidden until "Enable paid models" is on) ──
        CloudModel("openai/gpt-4o", "GPT-4o", "OpenAI flagship · multimodal", free=False),
        CloudModel("openai/gpt-4.1", "GPT-4.1", "OpenAI · strong coding + long context", free=False),
        CloudModel("anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6", "Anthropic workhorse · great coding", free=False),
        CloudModel("anthropic/claude-opus-4.8", "Claude Opus 4.8", "Anthropic flagship · deepest reasoning", free=False),
        CloudModel("google/gemini-2.5-pro", "Gemini 2.5 Pro", "Google flagship · long context", free=False),
        CloudModel("deepseek/deepseek-r1", "DeepSeek R1", "Strong open reasoning model", free=False),
        CloudModel("x-ai/grok-4.3", "Grok 4.3", "xAI flagship", free=False),
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


GROQ = Provider(
    key="groq",
    name="Groq",
    base_url="https://api.groq.com/openai/v1",
    env_var="CHATSTUDIO_GROQ_API_KEY",
    docs_url="https://console.groq.com/keys",
    models=(
        CloudModel(
            "llama-3.3-70b-versatile",
            "Llama 3.3 70B Versatile",
            "Strong generalist · 128K context · ~300+ tok/s",
        ),
        CloudModel(
            "llama-3.1-8b-instant",
            "Llama 3.1 8B Instant",
            "Fastest · great for quick replies",
        ),
        CloudModel(
            "openai/gpt-oss-120b",
            "GPT-OSS 120B",
            "OpenAI's open model · strong reasoning",
        ),
        CloudModel(
            "openai/gpt-oss-20b",
            "GPT-OSS 20B",
            "Smaller open model · very fast",
        ),
    ),
)


CEREBRAS = Provider(
    key="cerebras",
    name="Cerebras",
    base_url="https://api.cerebras.ai/v1",
    env_var="CHATSTUDIO_CEREBRAS_API_KEY",
    docs_url="https://cloud.cerebras.ai",
    models=(
        CloudModel(
            "llama3.1-8b",
            "Llama 3.1 8B",
            "Ultra-fast wafer-scale inference",
        ),
        CloudModel(
            "gpt-oss-120b",
            "GPT-OSS 120B",
            "OpenAI's open model · ~3000 tok/s",
        ),
        CloudModel(
            "qwen-3-235b-a22b-instruct-2507",
            "Qwen3 235B Instruct",
            "Large MoE · strong reasoning + coding",
        ),
    ),
)


GEMINI = Provider(
    key="gemini",
    name="Google Gemini",
    # OpenAI-compatible endpoint (no trailing slash — stream_chat appends
    # "/chat/completions"). Auth is a normal Bearer token.
    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    env_var="CHATSTUDIO_GEMINI_API_KEY",
    docs_url="https://aistudio.google.com/apikey",
    models=(
        CloudModel(
            "gemini-3.5-flash",
            "Gemini 3.5 Flash",
            "Latest flagship Flash · multimodal · big context",
        ),
        CloudModel(
            "gemini-3.1-flash-lite",
            "Gemini 3.1 Flash-Lite",
            "Fast + low-cost · frontier-class for its size",
        ),
        CloudModel(
            "gemini-2.5-flash",
            "Gemini 2.5 Flash",
            "Proven stable Flash model",
        ),
        # ── Paid (hidden until "Enable paid models" is on) ──
        CloudModel("gemini-2.5-pro", "Gemini 2.5 Pro", "Most capable Gemini · deep reasoning", free=False),
    ),
)


HFROUTER = Provider(
    key="hfrouter",
    name="Hugging Face Router",
    base_url="https://router.huggingface.co/v1",
    env_var="CHATSTUDIO_HFROUTER_API_KEY",
    docs_url="https://huggingface.co/settings/tokens",
    reuse_hf_token=True,   # uses your saved HF token if no separate key is set
    models=(
        CloudModel("Qwen/Qwen3.5-9B", "Qwen3.5 9B", "Small + fast"),
        CloudModel("Qwen/Qwen3.6-27B", "Qwen3.6 27B", "Strong mid-size generalist"),
        CloudModel("deepseek-ai/DeepSeek-V4-Flash", "DeepSeek V4 Flash", "Fast DeepSeek"),
        CloudModel("google/gemma-4-26B-A4B-it", "Gemma 4 26B (MoE)", "Efficient mixture-of-experts"),
        CloudModel("zai-org/GLM-5.2", "GLM 5.2", "Strong open frontier model"),
    ),
)


SAMBANOVA = Provider(
    key="sambanova",
    name="SambaNova",
    base_url="https://api.sambanova.ai/v1",
    env_var="CHATSTUDIO_SAMBANOVA_API_KEY",
    docs_url="https://cloud.sambanova.ai/apis",
    models=(
        CloudModel("Meta-Llama-3.3-70B-Instruct", "Llama 3.3 70B", "Fast generalist"),
        CloudModel("DeepSeek-V3.1", "DeepSeek V3.1", "Strong general chat"),
        CloudModel("DeepSeek-V3.2", "DeepSeek V3.2", "Latest DeepSeek V3"),
        CloudModel("gpt-oss-120b", "GPT-OSS 120B", "OpenAI's open model"),
        CloudModel("gemma-4-31B-it", "Gemma 4 31B", "Google's 31B instruct"),
        CloudModel("MiniMax-M2.7", "MiniMax M2.7", "MiniMax frontier model"),
    ),
)


GITHUB = Provider(
    key="github",
    name="GitHub Models",
    base_url="https://models.github.ai/inference",
    env_var="CHATSTUDIO_GITHUB_API_KEY",
    docs_url="https://github.com/settings/tokens",
    models=(
        CloudModel("openai/gpt-4o-mini", "GPT-4o mini", "Fast OpenAI model"),
        CloudModel("openai/gpt-4.1", "GPT-4.1", "Strong coding + long context"),
        CloudModel("openai/o4-mini", "o4-mini", "OpenAI reasoning"),
        CloudModel("meta/llama-3.3-70b-instruct", "Llama 3.3 70B", "Open generalist"),
        CloudModel("deepseek/deepseek-r1", "DeepSeek R1", "Open reasoning"),
        CloudModel("microsoft/phi-4", "Phi-4", "Small + capable"),
    ),
)


PROVIDERS: dict[str, Provider] = {
    p.key: p for p in (OPENROUTER, NVIDIA, GROQ, CEREBRAS, GEMINI, HFROUTER, SAMBANOVA, GITHUB)
}


def get_api_key(key: str) -> Optional[str]:
    """Env var wins, then settings.json, then (for HF Router) the saved
    Hugging Face token. Returns the trimmed key or None."""
    p = PROVIDERS.get(key)
    if not p:
        return None
    env = (os.environ.get(p.env_var) or "").strip()
    if env:
        return env
    stored = (app_settings.get_provider_key(key) or "").strip()
    if stored:
        return stored
    # HF Router authenticates with a Hugging Face token — reuse the one the
    # user already saved for downloads so they don't enter it twice.
    if p.reuse_hf_token:
        return app_settings.get_hf_token()
    return None


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


def paid_enabled(key: str) -> bool:
    """Whether the user has opted into this provider's paid models."""
    return bool(app_settings.get_provider_paid(key))


def model_allowed(provider: Provider, model: CloudModel) -> bool:
    """Free models are always allowed; paid models only when the provider's
    paid toggle is on. Guards the chat route so a paid model can't be used
    (and billed) until explicitly enabled."""
    return model.free or paid_enabled(provider.key)


def public_view() -> list[dict]:
    """Shape returned by GET /api/providers — never includes raw API keys.

    Returns ALL models (free + paid) each tagged with `free`, plus per-provider
    `has_paid` / `paid_enabled` so the UI can show free models by default and
    reveal paid ones only after the toggle is enabled."""
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
            "reuse_hf_token": p.reuse_hf_token,
            "has_paid": any(not m.free for m in p.models),
            "paid_enabled": paid_enabled(p.key),
            "models": [
                {"id": m.id, "label": m.label, "notes": m.notes, "free": m.free,
                 "repo": repo_id(p.key, m.id)}
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
