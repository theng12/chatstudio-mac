"""
Hugging Face Hub model search.

Lets the Models tab discover MLX models beyond the curated catalog. We query
the public HF models API filtered to the `mlx` tag (so results are actually
MLX-loadable on Apple Silicon), sorted by downloads. A saved HF token, if any,
is sent to lift anonymous rate limits.

Uses `httpx` (a huggingface_hub dependency, certifi-backed) so TLS verification
works in the bundled conda env, where stdlib urllib can't find a CA bundle.
"""
from __future__ import annotations

import httpx

from . import settings as app_settings

_API = "https://huggingface.co/api/models"


def search(query: str, limit: int = 40) -> list[dict]:
    """Return a list of MLX models matching `query`, most-downloaded first.

    Each item: {repo, downloads, likes, pipeline_tag, library_name}. An empty
    query returns the most popular MLX models. Raises on network/parse errors
    so the caller can surface a clean message.
    """
    limit = max(1, min(int(limit or 40), 80))
    params = {
        "filter": "mlx",
        "sort": "downloads",
        "direction": "-1",
        "limit": str(limit),
    }
    q = (query or "").strip()
    if q:
        params["search"] = q

    headers = {"User-Agent": "chat-studio-kh"}
    token = app_settings.get_hf_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = httpx.get(_API, params=params, headers=headers, timeout=15,
                     follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()

    # Drop clearly non-chat MLX models (ASR, TTS, embeddings, vision-only, image
    # generation). Empty / text / multimodal-LLM tags are kept, since Gemma 3/4
    # report image-text-to-text / any-to-any but run fine as text chat here.
    _NON_CHAT = {
        "automatic-speech-recognition", "text-to-speech", "audio-classification",
        "audio-to-audio", "feature-extraction", "sentence-similarity",
        "text-to-image", "image-to-image", "image-classification",
        "object-detection", "image-segmentation", "depth-estimation",
        "fill-mask", "token-classification",
    }
    out: list[dict] = []
    for m in data:
        repo = m.get("id") or m.get("modelId")
        if not repo:
            continue
        pt = m.get("pipeline_tag") or ""
        if pt in _NON_CHAT:
            continue
        out.append({
            "repo": repo,
            "downloads": m.get("downloads") or 0,
            "likes": m.get("likes") or 0,
            "pipeline_tag": pt,
            "library_name": m.get("library_name") or "",
        })
    return out
