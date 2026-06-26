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

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Iterator, Optional

from . import cache


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
    """Holds at most one loaded MLX chat model at a time.

    ── Threading model ──
    MLX arrays carry a thread/stream affinity: a model loaded on one thread
    cannot be evaluated on another (`mx.eval` raises "There is no Stream(gpu, N)
    in current thread"). FastAPI runs sync handlers in a threadpool and streams
    responses from yet another thread, so without care, load and generation land
    on different threads and crash. We therefore funnel ALL MLX work — load,
    generate, unload — through a single dedicated worker thread, so every GPU op
    for the engine happens on one consistent thread. Generation is serialized as
    a result, which is exactly what we want for a one-model-at-a-time local app.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: Optional[LoadedModel] = None
        self._load_error: Optional[str] = None
        # The single thread every MLX operation runs on.
        self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
        # Set to request the in-flight generation stop early (Stop button /
        # client disconnect). Checked each token by the generation loop.
        self._cancel = threading.Event()
        # Memory management: when the loaded local model sits unused (e.g. the
        # user switched to a cloud model), free it after an idle timeout.
        self._last_used: float = 0.0
        self._last_auto_unload: Optional[dict] = None

    def touch(self) -> None:
        self._last_used = time.time()

    def idle_seconds(self) -> Optional[float]:
        with self._lock:
            if self._loaded is None:
                return None
        return time.time() - self._last_used

    def last_auto_unload(self) -> Optional[dict]:
        return self._last_auto_unload

    def unload_if_idle(self, threshold_seconds: float) -> Optional[str]:
        """Unload the model if it's been idle longer than the threshold. Runs on
        the MLX worker thread; returns the repo it freed, or None."""
        return self._exec.submit(self._unload_if_idle_sync, threshold_seconds).result()

    def _unload_if_idle_sync(self, threshold: float) -> Optional[str]:
        with self._lock:
            if self._loaded is None:
                return None
            if (time.time() - self._last_used) < threshold:
                return None
            repo = self._loaded.repo
            self._loaded = None
            self._last_auto_unload = {"repo": repo, "at": time.time(), "reason": "idle"}
            try:
                import gc
                import mlx.core as mx
                gc.collect()
                mx.clear_cache()
            except Exception:
                pass
            return repo

    def loaded_repo(self) -> Optional[str]:
        with self._lock:
            return self._loaded.repo if self._loaded else None

    def is_loaded(self, repo: str) -> bool:
        with self._lock:
            return self._loaded is not None and self._loaded.repo == repo

    def last_error(self) -> Optional[str]:
        return self._load_error

    def load(self, repo: str) -> dict:
        """Load `repo` into memory (unloading any previous model first). Runs on
        the dedicated MLX worker thread; blocks the caller until done."""
        return self._exec.submit(self._load_sync, repo).result()

    def ensure_loaded(self, repo: Optional[str]) -> str:
        """Make `repo` the active model, loading it on demand if it's cached but
        not loaded. Lets the OpenAI-compatible `/v1` endpoint work as a drop-in
        server (request a model → it loads itself), instead of requiring an
        explicit /api/chat/load first. Returns the repo that is now loaded.
        Raises RuntimeError if no usable model can be made ready."""
        if not repo:
            current = self.loaded_repo()
            if current is None:
                raise RuntimeError(
                    "No model is loaded and none was specified. Load one first "
                    "(POST /api/chat/load) or pass a model id."
                )
            return current
        if self.is_loaded(repo):
            return repo
        if cache.cache_state(repo) != "cached":
            raise RuntimeError(
                f"Model {repo} is not downloaded on this server. "
                f"Download it from the Models tab first."
            )
        self.load(repo)
        return repo

    def cancel(self) -> bool:
        """Ask the in-flight generation to stop at the next token. No-op if
        nothing is generating."""
        self._cancel.set()
        return True

    def _load_sync(self, repo: str) -> dict:
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
            self._last_used = time.time()
            return {"repo": repo, "already_loaded": False}

    def unload(self) -> bool:
        return self._exec.submit(self._unload_sync).result()

    def _unload_sync(self) -> bool:
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
        """Yields text chunks as the model generates.

        The actual MLX generation runs on the manager's single worker thread —
        the SAME thread the model was loaded on — because MLX arrays are
        thread/stream-bound. Prompt building (tokenizer only, no GPU work) runs
        on the caller's thread; generated text is bridged back over a queue, so
        this stays a simple synchronous iterator for callers."""
        self.touch()  # mark in-use so the idle auto-unload timer resets
        loaded, prompt = self.build_prompt(repo, messages)

        chunks: "queue.Queue" = queue.Queue()
        _DONE = object()

        def _generate():
            # Reset cancellation on the worker right before generating, so a
            # second request arriving while this one is queued can't clear a
            # cancel meant for the generation that's actually running.
            self._cancel.clear()
            try:
                from mlx_lm import stream_generate
                from mlx_lm.sample_utils import make_sampler
                sampler = make_sampler(temp=temperature, top_p=top_p)
                for response in stream_generate(
                    loaded.model, loaded.tokenizer, prompt,
                    max_tokens=max_tokens, sampler=sampler,
                ):
                    text = getattr(response, "text", None)
                    if text:
                        chunks.put(("chunk", text))
                    # Stop generating as soon as a cancel is requested — this is
                    # what actually frees the GPU, not just closing the socket.
                    if self._cancel.is_set():
                        break
                chunks.put((_DONE, None))
            except Exception as e:  # surfaced to the caller below
                chunks.put(("error", e))

        future = self._exec.submit(_generate)
        try:
            while True:
                kind, payload = chunks.get()
                if kind == "chunk":
                    yield payload
                elif kind == "error":
                    raise RuntimeError(str(payload))
                else:
                    break
        except GeneratorExit:
            # The consumer went away (client disconnect or Stop closed the
            # response) — tell the worker to stop instead of generating to
            # max_tokens in the background.
            self._cancel.set()
            raise
        finally:
            # Make sure the worker stops and finishes, freeing the single worker
            # thread for the next request (and propagating any failure).
            self._cancel.set()
            future.result()

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
