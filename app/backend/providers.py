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
    live_free_only: bool = False   # when live-fetching, keep only free models (OpenRouter)
    # When True, /v1/models fetches the provider's live /models endpoint
    # (TTL-cached) instead of using the curated `models` tuple. Reserved for
    # providers whose catalog drifts often or is too large to curate by hand
    # (OpenRouter ships hundreds). Static providers get the curated list,
    # which is faster and avoids hammering their API on every listing call.
    supports_live_listing: bool = False


OPENROUTER = Provider(
    key="openrouter",
    name="OpenRouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="CHATSTUDIO_OPENROUTER_API_KEY",
    docs_url="https://openrouter.ai/keys",
    supports_live_listing=True,
    live_free_only=True,   # its live catalog is 300+; surface only the :free tier
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
    # NVIDIA NIM hosts 100+ models free for developers. This is a curated slice
    # of the most useful chat/coding/reasoning ones (all verified present in the
    # live catalog); the "Load all models" button fetches the full list.
    #
    # Live-listed because NVIDIA retires hosted models on a schedule (e.g.
    # gemma-3-27b-it went 410 Gone on 2026-05-12 while still curated here, so
    # /v1/models advertised an id that 502'd on use — hit by Story Studio).
    # With live listing, /v1/models serves NVIDIA's actual current catalog
    # (60s TTL cache); the curated list below is the offline/error fallback.
    supports_live_listing=True,
    models=(
        # ── Llama family ──
        CloudModel("meta/llama-3.3-70b-instruct", "Llama 3.3 70B", "Strong generalist"),
        CloudModel("meta/llama-3.1-70b-instruct", "Llama 3.1 70B", "Generalist"),
        CloudModel("meta/llama-3.1-8b-instruct", "Llama 3.1 8B", "Fast small model"),
        CloudModel("meta/llama-3.2-3b-instruct", "Llama 3.2 3B", "Tiny + fast"),
        CloudModel("meta/llama-4-maverick-17b-128e-instruct", "Llama 4 Maverick", "MoE · long context"),
        # ── NVIDIA Nemotron (reasoning-tuned) ──
        CloudModel("nvidia/llama-3.3-nemotron-super-49b-v1.5", "Nemotron Super 49B v1.5", "Reasoning-tuned"),
        CloudModel("nvidia/llama-3.1-nemotron-70b-instruct", "Nemotron 70B", "Reasoning-tuned Llama"),
        CloudModel("nvidia/llama-3.1-nemotron-ultra-253b-v1", "Nemotron Ultra 253B", "Top-tier reasoning"),
        CloudModel("nvidia/nemotron-3-super-120b-a12b", "Nemotron-3 Super 120B", "MoE · strong reasoning"),
        CloudModel("nvidia/nvidia-nemotron-nano-9b-v2", "Nemotron Nano 9B v2", "Small + fast"),
        CloudModel("nvidia/nemotron-4-340b-instruct", "Nemotron-4 340B", "Flagship dense"),
        # ── Qwen ──
        CloudModel("qwen/qwen3-next-80b-a3b-instruct", "Qwen3-Next 80B", "MoE generalist"),
        CloudModel("qwen/qwen3.5-397b-a17b", "Qwen3.5 397B", "Large MoE"),
        # ── DeepSeek ──
        CloudModel("deepseek-ai/deepseek-v4-pro", "DeepSeek V4 Pro", "Frontier reasoning"),
        CloudModel("deepseek-ai/deepseek-v4-flash", "DeepSeek V4 Flash", "Fast DeepSeek"),
        # ── Mistral ──
        CloudModel("mistralai/mistral-large-3-675b-instruct-2512", "Mistral Large 3", "Flagship"),
        CloudModel("mistralai/mistral-small-4-119b-2603", "Mistral Small 4", "Efficient generalist"),
        CloudModel("mistralai/mistral-nemotron", "Mistral Nemotron", "NVIDIA-tuned Mistral"),
        CloudModel("mistralai/codestral-22b-instruct-v0.1", "Codestral 22B", "Code-focused"),
        # ── Google Gemma ──
        CloudModel("google/gemma-4-31b-it", "Gemma 4 31B", "Google's latest"),
        CloudModel("google/gemma-3-12b-it", "Gemma 3 12B", "Mid-size Gemma"),
        # ── OpenAI open models ──
        CloudModel("openai/gpt-oss-120b", "GPT-OSS 120B", "OpenAI open model"),
        CloudModel("openai/gpt-oss-20b", "GPT-OSS 20B", "Smaller open model"),
        # ── Microsoft Phi ──
        CloudModel("microsoft/phi-4-mini-instruct", "Phi-4 Mini", "Small + capable"),
        CloudModel("microsoft/phi-3.5-moe-instruct", "Phi-3.5 MoE", "Mixture-of-experts"),
        # ── Others ──
        CloudModel("moonshotai/kimi-k2.6", "Kimi K2.6", "Long-context generalist"),
        CloudModel("ibm/granite-3.0-8b-instruct", "Granite 3.0 8B", "IBM enterprise model"),
        CloudModel("ibm/granite-34b-code-instruct", "Granite 34B Code", "Code-focused"),
        CloudModel("01-ai/yi-large", "Yi Large", "Strong bilingual (EN/中文)"),
        CloudModel("ai21labs/jamba-1.5-large-instruct", "Jamba 1.5 Large", "Hybrid SSM · long context"),
        CloudModel("databricks/dbrx-instruct", "DBRX", "Databricks MoE"),
        CloudModel("bigcode/starcoder2-15b", "StarCoder2 15B", "Code generation"),
    ),
)


GROQ = Provider(
    key="groq",
    name="Groq",
    base_url="https://api.groq.com/openai/v1",
    env_var="CHATSTUDIO_GROQ_API_KEY",
    docs_url="https://console.groq.com/keys",
    supports_live_listing=True,
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
    supports_live_listing=True,
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
    supports_live_listing=True,
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
    supports_live_listing=True,
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
    supports_live_listing=True,
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
    supports_live_listing=True,
    models=(
        CloudModel("openai/gpt-4o-mini", "GPT-4o mini", "Fast OpenAI model"),
        CloudModel("openai/gpt-4.1", "GPT-4.1", "Strong coding + long context"),
        CloudModel("openai/o4-mini", "o4-mini", "OpenAI reasoning"),
        CloudModel("meta/llama-3.3-70b-instruct", "Llama 3.3 70B", "Open generalist"),
        CloudModel("deepseek/deepseek-r1", "DeepSeek R1", "Open reasoning"),
        CloudModel("microsoft/phi-4", "Phi-4", "Small + capable"),
    ),
)


# ═══════════ Paid / official providers ═══════════
# These bill per token from the user's own account. Every model is marked
# free=False, so nothing here is listed or routable until the user flips the
# provider's "Enable paid models" toggle in Settings — same guard the paid
# OpenRouter flagships already use. (OpenCode Zen is the exception: it ships
# a few genuinely free models, marked free=True below.)

OPENAI = Provider(
    key="openai",
    name="OpenAI (official)",
    base_url="https://api.openai.com/v1",
    env_var="CHATSTUDIO_OPENAI_API_KEY",
    docs_url="https://platform.openai.com/api-keys",
    supports_live_listing=True,
    models=(
        CloudModel("gpt-5.5", "GPT-5.5", "Flagship", free=False),
        CloudModel("gpt-5.4", "GPT-5.4", "Strong generalist", free=False),
        CloudModel("gpt-5.4-mini", "GPT-5.4 mini", "Fast + affordable", free=False),
        CloudModel("gpt-5.4-nano", "GPT-5.4 nano", "Cheapest tier", free=False),
        CloudModel("gpt-5.3-codex", "GPT-5.3 Codex", "Code-focused", free=False),
        CloudModel("gpt-4.1", "GPT-4.1", "Proven stable · long context", free=False),
    ),
)


ANTHROPIC = Provider(
    key="anthropic",
    name="Anthropic (official)",
    # Anthropic's OpenAI-SDK compatibility layer: /v1/chat/completions works
    # with a normal Bearer token. Their /v1/models listing uses the native
    # x-api-key auth instead, so live listing is off — curated list only.
    base_url="https://api.anthropic.com/v1",
    env_var="CHATSTUDIO_ANTHROPIC_API_KEY",
    docs_url="https://console.anthropic.com/settings/keys",
    models=(
        CloudModel("claude-fable-5", "Claude Fable 5", "Newest generation", free=False),
        CloudModel("claude-opus-4-8", "Claude Opus 4.8", "Deepest reasoning", free=False),
        CloudModel("claude-sonnet-5", "Claude Sonnet 5", "Workhorse · great coding", free=False),
        CloudModel("claude-haiku-4-5", "Claude Haiku 4.5", "Fast + affordable", free=False),
    ),
)


DEEPSEEK = Provider(
    key="deepseek",
    name="DeepSeek (official)",
    base_url="https://api.deepseek.com/v1",
    env_var="CHATSTUDIO_DEEPSEEK_API_KEY",
    docs_url="https://platform.deepseek.com/api_keys",
    supports_live_listing=True,
    models=(
        CloudModel("deepseek-chat", "DeepSeek Chat", "Latest V-series chat model", free=False),
        CloudModel("deepseek-reasoner", "DeepSeek Reasoner", "Reasoning (R-series)", free=False),
    ),
)


OPENCODE = Provider(
    key="opencode",
    name="OpenCode Zen",
    # Coding-focused model gateway (opencode.ai). OpenAI-style
    # /chat/completions; their /models endpoint is metadata-shaped rather
    # than OpenAI-shaped, so live listing is off — curated list only.
    base_url="https://opencode.ai/zen/v1",
    env_var="CHATSTUDIO_OPENCODE_API_KEY",
    docs_url="https://opencode.ai/auth",
    models=(
        # ── Free tier ──
        CloudModel("big-pickle", "Big Pickle (free)", "Free coding model"),
        CloudModel("nemotron-3-ultra-free", "Nemotron-3 Ultra (free)", "Free reasoning"),
        CloudModel("deepseek-v4-flash-free", "DeepSeek V4 Flash (free)", "Free · fast"),
        CloudModel("mimo-v2.5-free", "MiMo v2.5 (free)", "Free small model"),
        # ── Paid (billed against your OpenCode credit) ──
        CloudModel("gpt-5.3-codex", "GPT-5.3 Codex", "Code-focused OpenAI", free=False),
        CloudModel("claude-sonnet-5", "Claude Sonnet 5", "Strong coding", free=False),
        CloudModel("kimi-k2.7-code", "Kimi K2.7 Code", "Code-tuned Kimi", free=False),
        CloudModel("qwen3.7-max", "Qwen3.7 Max", "Alibaba flagship", free=False),
        CloudModel("glm-5.2", "GLM 5.2", "Strong open frontier", free=False),
        CloudModel("deepseek-v4-pro", "DeepSeek V4 Pro", "Frontier reasoning", free=False),
        CloudModel("minimax-m3", "MiniMax M3", "MiniMax frontier", free=False),
    ),
)


PROVIDERS: dict[str, Provider] = {
    p.key: p for p in (
        OPENROUTER, NVIDIA, GROQ, CEREBRAS, GEMINI, HFROUTER, SAMBANOVA, GITHUB,
        OPENAI, ANTHROPIC, DEEPSEEK, OPENCODE,
    )
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
    # On an all-paid provider (OpenAI/Anthropic/DeepSeek official) every
    # unknown model is still paid — mark it so the paid gate applies rather
    # than letting a novel id bill the user without the toggle.
    return p, CloudModel(id=model_id, label=model_id, free=not all_paid(p))


def paid_enabled(key: str) -> bool:
    """Whether the user has opted into this provider's paid models."""
    return bool(app_settings.get_provider_paid(key))


def model_allowed(provider: Provider, model: CloudModel) -> bool:
    """Free models are always allowed; paid models only when the provider's
    paid toggle is on. Guards the chat route so a paid model can't be used
    (and billed) until explicitly enabled."""
    return model.free or paid_enabled(provider.key)


def all_paid(provider: Provider) -> bool:
    """True when every curated model is paid (official OpenAI/Anthropic/
    DeepSeek). Such a provider is hidden from listings entirely — and its
    live-listed ids are paid-gated — until the paid toggle is on."""
    return bool(provider.models) and all(not m.free for m in provider.models)


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


_NON_CHAT_HINTS = (
    "embedding", "whisper", "tts", "text-to-speech", "stable-diffusion",
    "-image", "image-", "rerank", "moderation", "guard", "bge-", "-bge",
    "clip", "transcribe", "audio", "vision-encoder",
    # non-chat categories seen in NVIDIA NIM's catalog
    "embed", "reward", "content-safety", "retriev", "translate",
    "-parse", "gliner", "video-detector", "deplot", "kosmos",
    # non-chat entries in OpenAI's /models (legacy bases, image, realtime)
    "dall-e", "davinci", "babbage", "realtime", "-instruct-0914",
)


def _is_free_model(m: dict) -> bool:
    """Free marker for a mixed free+paid catalog (OpenRouter): the explicit
    `:free` model-id suffix. We deliberately do NOT treat "prompt price == 0"
    as free — some zero-prompt-priced entries are non-chat (e.g. the Lyria
    music model, priced per-second) or meta-routers (`openrouter/free`)."""
    mid = (m.get("id") or "") if isinstance(m, dict) else str(m)
    return mid.endswith(":free")


# ─── Live-listing TTL cache (used by /v1/models for dynamic providers) ───
# Maps provider.key → (fetched_at_epoch, [{"id":..., "repo":...}, ...]).
# 60s is short enough that newly-added cloud models surface quickly while
# still preventing /v1/models from hammering upstream on every call.
_LIVE_CACHE: dict[str, tuple[float, list[dict]]] = {}
_LIVE_CACHE_TTL_S = 60.0


def _static_models(provider: Provider) -> list[dict]:
    """The curated catalog (respecting the paid gate) in the {id, repo}
    shape /v1/models expects."""
    return [
        {"id": m.id, "repo": repo_id(provider.key, m.id)}
        for m in provider.models
        if model_allowed(provider, m)
    ]


async def _cached_live_models(provider: Provider) -> Optional[list[dict]]:
    """Raw live fetch behind the TTL cache. Returns None (also cached, so a
    flapping upstream isn't retried on every call) when the fetch fails."""
    now = time.time()
    cached = _LIVE_CACHE.get(provider.key)
    if cached and (now - cached[0]) < _LIVE_CACHE_TTL_S:
        return cached[1]
    try:
        models = await list_live_models(provider)
    except Exception:
        models = None
    _LIVE_CACHE[provider.key] = (now, models)
    return models


async def models_for_provider(provider: Provider) -> list[dict]:
    """Return [{id, repo}, ...] for a provider: live-fetch (TTL-cached) for
    providers flagged `supports_live_listing`, curated static list otherwise,
    always respecting the paid gate. Never raises — /v1/models can safely
    fan out across all providers.

    Paid filtering happens HERE, per call — not inside the cache — so
    flipping a provider's paid toggle takes effect on the next request
    instead of after the TTL expires.
    """
    # All-paid provider (official OpenAI/Anthropic/DeepSeek) with the paid
    # toggle off: hide entirely. No key alone isn't consent to spend money.
    if all_paid(provider) and not paid_enabled(provider.key):
        return []

    if not provider.supports_live_listing:
        return _static_models(provider)

    live = await _cached_live_models(provider)
    if live is None:
        return _static_models(provider)

    curated = {m.id: m for m in provider.models}
    # Drop live ids whose curated entry says paid while the toggle is off
    # (e.g. Gemini's live list includes gemini-2.5-pro, curated as paid) —
    # otherwise we'd advertise a model the chat route would 403.
    out = [
        e for e in live
        if e["id"] not in curated or model_allowed(provider, curated[e["id"]])
    ]
    # Append allowed curated models the live list didn't include — this is
    # how OpenRouter's paid flagships surface once its paid toggle is on
    # (its live fetch is free-only by design).
    seen = {e["id"] for e in out}
    for m in provider.models:
        if m.id not in seen and model_allowed(provider, m):
            out.append({"id": m.id, "repo": repo_id(provider.key, m.id)})
    return out


async def list_live_models(provider: Provider) -> list[dict]:
    """Fetch the provider's CURRENT model catalog from its OpenAI-compatible
    `/models` endpoint, so the UI can show live models instead of a hardcoded
    list (ends the model-id drift problem). The API key is sent when available
    but isn't required for providers whose catalog is public. Obvious non-chat
    models (embeddings, speech, image) are filtered out. Raises RuntimeError on
    auth/HTTP errors so the caller can surface a clean message."""
    url = f"{provider.base_url}/models"
    headers = {"Accept": "application/json"}
    api_key = get_api_key(provider.key)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers)
    if r.status_code in (401, 403):
        raise RuntimeError(f"{provider.name} requires an API key to list models.")
    if r.status_code >= 400:
        raise RuntimeError(f"{provider.name} returned HTTP {r.status_code}: {(r.text or '')[:160]}")
    data = r.json()
    items = data.get("data", data) if isinstance(data, dict) else data
    out, seen = [], set()
    for m in (items or []):
        mid = m.get("id") if isinstance(m, dict) else (m if isinstance(m, str) else None)
        if not mid:
            continue
        # Gemini's OpenAI-compat /models returns ids as "models/gemini-…";
        # its /chat/completions accepts the bare id, and the bare form keeps
        # our synthetic provider:key:id repos consistent across providers.
        if mid.startswith("models/"):
            mid = mid[len("models/"):]
        if mid in seen:
            continue
        low = mid.lower()
        if any(h in low for h in _NON_CHAT_HINTS):
            continue
        # Providers whose catalog mixes free + paid (OpenRouter) → free only,
        # so we don't dump 300+ mostly-paid models into the picker.
        if provider.live_free_only and not _is_free_model(m):
            continue
        seen.add(mid)
        out.append({"id": mid, "repo": repo_id(provider.key, mid)})
    out.sort(key=lambda d: d["id"].lower())
    return out


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
