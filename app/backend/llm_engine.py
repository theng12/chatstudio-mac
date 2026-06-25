"""
LLM engine — loading and serving MLX chat models.

Keeps at most ONE model loaded in memory at a time (unified-memory budget
management — Apple Silicon shares RAM between CPU and GPU, so juggling
multiple multi-GB models loaded simultaneously is a fast way to OOM). Loading
a new model unloads whatever was previously loaded first.

Generation goes through `mlx_lm.stream_generate`, using the model's own chat
template (`tokenizer.apply_chat_template`) to turn an OpenAI-style messages
list into the prompt string the model expects. This mirrors what
`mlx_lm.server` does internally, but trimmed down to exactly what this app's
/api/chat and /v1/chat/completions endpoints need.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional

from . import cache


def _init_metal() -> None:
    """Ensure the Metal GPU stream is initialized on the calling thread.
    MLX Metal streams are thread-local — any thread that performs GPU ops
    must initialize its own stream first. Safe to call multiple times."""
    import mlx.core as mx
    mx.default_stream(mx.gpu)


def availability() -> dict:
    """Whether mlx-lm (and mlx) are importable on this machine. Mirrors the
    shape of VoiceStudio's generation.availability() — used by the frontend
    to show an install/diagnostics banner instead of a confusing 500 if the
    AI bundle hasn't finished installing yet."""
    out = {"available": False, "mlx": None, "mlx_lm": None, "error": None}
    try:
        import mlx.core as mx  # noqa: F401
        import mlx
        out["mlx"] = getattr(mlx, "__version__", "unknown")
    except Exception as e:
        out["error"] = f"mlx not importable: {e}"
        return out
    try:
        import mlx_lm
        out["mlx_lm"] = getattr(mlx_lm, "__version__", "unknown")
    except Exception as e:
        out["error"] = f"mlx_lm not importable: {e}"
        return out
    out["available"] = True
    return out


def diagnostics() -> dict:
    """Per-package health check, surfaced at /api/chat/diagnostics. Same
    spirit as VoiceStudio's generation.diagnostics() but scoped to the much
    smaller MLX-only dependency set this app needs."""
    avail = availability()
    packages = []
    for pkg in ("mlx", "mlx_lm", "huggingface_hub"):
        try:
            mod = __import__(pkg)
            packages.append({
                "package": pkg,
                "installed": True,
                "version": getattr(mod, "__version__", None),
                "error": None,
                "role": {
                    "mlx": "Apple Silicon array/ML framework (Metal-backed)",
                    "mlx_lm": "Loads + runs MLX-quantized chat models",
                    "huggingface_hub": "Downloads model repos from Hugging Face",
                }.get(pkg, ""),
            })
        except Exception as e:
            packages.append({
                "package": pkg, "installed": False, "version": None,
                "error": str(e), "role": "",
            })
    return {
        "available": avail["available"],
        "error": avail["error"],
        "packages": packages,
        "loaded_model": manager.loaded_repo(),
    }


@dataclass
class LoadedModel:
    repo: str
    model: object
    tokenizer: object
    loaded_at: float = field(default_factory=time.time)


class LLMManager:
    """Holds at most one loaded MLX chat model at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: Optional[LoadedModel] = None
        self._load_error: Optional[str] = None

    def loaded_repo(self) -> Optional[str]:
        with self._lock:
            return self._loaded.repo if self._loaded else None

    def is_loaded(self, repo: str) -> bool:
        with self._lock:
            return self._loaded is not None and self._loaded.repo == repo

    def last_error(self) -> Optional[str]:
        return self._load_error

    def load(self, repo: str) -> dict:
        """Load `repo` into memory, unloading whatever was loaded before it.
        Blocking — callers should run this off the request thread if they
        care about not blocking other requests during a multi-GB load."""
        # Ensure Metal is initialized on this thread — mlx_load does GPU
        # work and Uvicorn may dispatch sync handlers onto its thread pool.
        _init_metal()
        with self._lock:
            if self._loaded is not None and self._loaded.repo == repo:
                return {"repo": repo, "already_loaded": True}

            # Unload the previous model first so we never hold two multi-GB
            # models in unified memory at once.
            if self._loaded is not None:
                self._loaded = None
                try:
                    import gc
                    import mlx.core as mx
                    gc.collect()
                    mx.clear_cache()
                except Exception:
                    pass

            try:
                from mlx_lm import load as mlx_load
            except Exception as e:
                self._load_error = f"mlx_lm not importable: {e}"
                raise RuntimeError(self._load_error) from e

            try:
                model, tokenizer = mlx_load(repo)
            except Exception as e:
                self._load_error = f"failed to load {repo}: {e}"
                raise RuntimeError(self._load_error) from e

            self._loaded = LoadedModel(repo=repo, model=model, tokenizer=tokenizer)
            self._load_error = None
            return {"repo": repo, "already_loaded": False}

    def unload(self) -> bool:
        _init_metal()
        with self._lock:
            if self._loaded is None:
                return False
            self._loaded = None
            try:
                import gc
                import mlx.core as mx
                gc.collect()
                mx.clear_cache()
            except Exception:
                pass
            return True

    def _require_loaded(self, repo: Optional[str]) -> LoadedModel:
        with self._lock:
            if self._loaded is None:
                raise RuntimeError("No model is loaded. Call /api/chat/load first.")
            if repo and self._loaded.repo != repo:
                raise RuntimeError(
                    f"Requested model {repo!r} is not loaded — "
                    f"currently loaded: {self._loaded.repo!r}. Load it first."
                )
            return self._loaded

    def build_prompt(self, repo: Optional[str], messages: list[dict]) -> tuple[LoadedModel, str]:
        loaded = self._require_loaded(repo)
        tokenizer = loaded.tokenizer

        def apply(msgs: list[dict]) -> str:
            return tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True,
            )

        # 1) Try the messages as-is (the common path).
        try:
            return loaded, apply(messages)
        except Exception:
            pass

        # 2) Some chat templates (notably Gemma) reject a `system` role and
        #    raise. Merge the system prompt into the first user turn and retry
        #    so a user-set system prompt still takes effect on those models.
        if messages and messages[0].get("role") == "system":
            sys_txt = (messages[0].get("content") or "").strip()
            rest = messages[1:]
            merged: list[dict] = []
            injected = False
            for m in rest:
                if not injected and m.get("role") == "user":
                    user_txt = m.get("content") or ""
                    merged.append({
                        "role": "user",
                        "content": (sys_txt + "\n\n" + user_txt).strip() if sys_txt else user_txt,
                    })
                    injected = True
                else:
                    merged.append(m)
            if not injected and sys_txt:
                merged = [{"role": "user", "content": sys_txt}] + rest
            try:
                return loaded, apply(merged)
            except Exception:
                pass

        # 3) Last-resort fallback for tokenizers without a usable chat template —
        #    join turns plainly so generation still works, just without the
        #    model's preferred special tokens.
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"{role}: {content}")
        parts.append("assistant:")
        return loaded, "\n".join(parts)

    def stream_chat(
        self,
        repo: Optional[str],
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        top_p: float = 1.0,
    ) -> Iterator[str]:
        """Yields text chunks as the model generates. Uses mlx_lm.stream_generate
        under the hood — each yielded item's `.text` is the newly generated
        delta since the previous chunk."""
        loaded, prompt = self.build_prompt(repo, messages)
        try:
            from mlx_lm import stream_generate
            from mlx_lm.sample_utils import make_sampler
        except Exception as e:
            raise RuntimeError(f"mlx_lm not importable: {e}") from e

        # MLX Metal GPU streams are thread-local. If this method is called from
        # a background thread (as it is in the streaming endpoint), the Metal
        # context must be initialized explicitly on this thread.
        _init_metal()

        sampler = make_sampler(temp=temperature, top_p=top_p)
        for response in stream_generate(
            loaded.model, loaded.tokenizer, prompt,
            max_tokens=max_tokens, sampler=sampler,
        ):
            text = getattr(response, "text", None)
            if text:
                yield text

    def chat_once(
        self,
        repo: Optional[str],
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        top_p: float = 1.0,
    ) -> str:
        """Non-streaming convenience wrapper — joins the full stream into one
        string. Used by callers that don't need token-by-token output."""
        return "".join(
            self.stream_chat(repo, messages, temperature, max_tokens, top_p)
        )


manager = LLMManager()


def list_chat_models() -> list[dict]:
    """Every fully-cached model that can be loaded right now, for the Chat tab's
    picker. Lists the curated catalog models first (with their friendly labels),
    then any other cached repo the user downloaded via Hub search (labeled by
    its repo name). Each entry reports whether it's the currently loaded model."""
    from . import catalog
    out = []
    seen = set()
    for m in catalog.CATALOG:
        if cache.cache_state(m.repo) != "cached":
            continue
        out.append({
            "repo": m.repo,
            "label": m.label,
            "loaded": manager.is_loaded(m.repo),
            "in_catalog": True,
        })
        seen.add(m.repo)
    for repo in cache.list_cached_repos():
        if repo in seen:
            continue
        out.append({
            "repo": repo,
            "label": repo.split("/")[-1],
            "loaded": manager.is_loaded(repo),
            "in_catalog": False,
        })
    return out
