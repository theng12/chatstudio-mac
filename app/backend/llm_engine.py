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

import base64
import os
import queue
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from . import cache

_MAX_IMAGES = 4
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
MEMORY_RETRY_LIMIT = 1
MEMORY_RESTART_FAILURES = 2


def _memory_snapshot() -> Optional[dict]:
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / 1e9, 2),
            "available_gb": round(vm.available / 1e9, 2),
            "used_gb": round(vm.used / 1e9, 2),
            "percent": float(vm.percent),
        }
    except Exception:
        return None


def _is_memory_failure(exc: BaseException) -> bool:
    """Recognize allocator failures without treating provider/input errors as OOM."""
    if isinstance(exc, MemoryError):
        return True
    message = f"{type(exc).__name__}: {exc}".lower()
    return any(
        marker in message
        for marker in (
            "out of memory",
            "out-of-memory",
            "cannot allocate memory",
            "failed to allocate memory",
            "metal allocation failed",
            "mlx allocation failed",
            "std::bad_alloc",
        )
    )


def _decode_images(images: Optional[list]) -> tuple[list, list]:
    """Turn the frontend's image payloads into file paths mlx-vlm can read.

    Accepts data URLs (`data:image/png;base64,…`) or bare base64. Remote URLs
    are intentionally rejected so this LAN-facing API cannot be used for SSRF.
    Returns temporary file paths that the caller must delete afterwards."""
    paths: list = []
    temp_paths: list = []
    if len(images or []) > _MAX_IMAGES:
        raise ValueError(f"Attach at most {_MAX_IMAGES} images per message")
    for img in images or []:
        if not isinstance(img, str) or not img.strip():
            raise ValueError("Each image must be a base64 string or data URL")
        s = img.strip()
        if s.startswith("http://") or s.startswith("https://"):
            raise ValueError("Remote image URLs are not accepted; upload the image data instead")
        m = re.match(r"data:image/([\w.+-]+);base64,(.*)$", s, re.DOTALL)
        if m:
            ext, b64 = m.group(1), m.group(2)
        else:
            ext, b64 = "png", s
        if ext == "jpeg":
            ext = "jpg"
        if ext not in {"png", "jpg", "webp"}:
            raise ValueError(f"Unsupported image type: {ext}")
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception as e:
            raise ValueError("Image payload is not valid base64") from e
        if len(raw) > _MAX_IMAGE_BYTES:
            raise ValueError("Each image must be 10 MB or smaller")
        fd, path = tempfile.mkstemp(suffix=f".{ext}", prefix="chatstudio-img-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(raw)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        paths.append(path)
        temp_paths.append(path)
    return paths, temp_paths


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


def vlm_available() -> bool:
    """Whether mlx-vlm is importable — the engine for vision-language models
    (e.g. the Qwen3.5 family). Optional: text-only chat works without it, so a
    missing mlx-vlm only disables vision models, it doesn't break the app."""
    try:
        import mlx_vlm  # noqa: F401
        return True
    except Exception:
        return False


def diagnostics() -> dict:
    """Per-package health check, surfaced at /api/chat/diagnostics. Same
    spirit as VoiceStudio's generation.diagnostics() but scoped to the much
    smaller MLX-only dependency set this app needs."""
    avail = availability()
    packages = []
    for pkg in ("mlx", "mlx_lm", "mlx_vlm", "huggingface_hub"):
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
                    "mlx_vlm": "Vision-language engine (image+text models, e.g. Qwen3.5)",
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
    tokenizer: object          # tokenizer (text) OR processor (vision)
    loaded_at: float = field(default_factory=time.time)
    kind: str = "text"         # "text" (mlx-lm) | "vlm" (mlx-vlm)
    config: object = None       # model config — mlx-vlm's apply_chat_template needs it


@dataclass(frozen=True)
class ChatGenerationResult:
    """One complete local response with tokenizer-native usage evidence."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str
    peak_memory: float | None = None


def is_vision_model(repo: str) -> bool:
    """True if `repo` is a vision-language model that must load through mlx-vlm
    instead of mlx-lm. An explicit catalog flag is fast, but curated text
    entries are still checked against cached config.json so metadata cannot
    hide a real vision architecture."""
    try:
        from . import catalog
        for m in catalog.CATALOG:
            if m.repo == repo and getattr(m, "is_vision", False):
                return True
            if m.repo == repo:
                break
    except Exception:
        pass
    # Sniff the downloaded config.json under the HF snapshot.
    try:
        import json
        snaps = cache.repo_cache_dir(repo) / "snapshots"
        if snaps.exists():
            for snap in snaps.iterdir():
                cfg_path = snap / "config.json"
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text())
                    if "vision_config" in cfg:
                        return True
                    archs = cfg.get("architectures") or []
                    if any("ForConditionalGeneration" in a for a in archs):
                        return True
                    break
    except Exception:
        pass
    return False


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
        self._busy = threading.Event()
        # Memory management: when the loaded local model sits unused (e.g. the
        # user switched to a cloud model), free it after an idle timeout.
        self._last_used: float = 0.0
        self._last_auto_unload: Optional[dict] = None
        self._consecutive_memory_failures = 0
        self._last_memory_event: Optional[dict] = None
        self._restart_scheduled = False
        self._restart_timer_started = False

    def touch(self) -> None:
        self._last_used = time.time()

    def idle_seconds(self) -> Optional[float]:
        with self._lock:
            if self._loaded is None:
                return None
        return time.time() - self._last_used

    def last_auto_unload(self) -> Optional[dict]:
        return self._last_auto_unload

    def memory_status(self) -> dict:
        return {
            "snapshot": _memory_snapshot(),
            "consecutive_failures": self._consecutive_memory_failures,
            "restart_scheduled": self._restart_scheduled,
            "last_event": self._last_memory_event,
            "service_supervised": self._service_installed(),
        }

    def is_busy(self) -> bool:
        """True while a model load or queued/running generation owns MLX."""
        return self._busy.is_set()

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
        def _load_with_recovery() -> dict:
            for attempt in range(MEMORY_RETRY_LIMIT + 1):
                try:
                    result = self._load_sync(repo)
                    self._consecutive_memory_failures = 0
                    return result
                except Exception as exc:
                    if not _is_memory_failure(exc):
                        self._consecutive_memory_failures = 0
                        raise
                    self._record_memory_failure_sync(exc)
                    if attempt < MEMORY_RETRY_LIMIT and not self._restart_scheduled:
                        print(
                            "[chat] retrying local model load once after memory recovery",
                            file=sys.stderr,
                            flush=True,
                        )
                        continue
                    if self._restart_scheduled:
                        raise RuntimeError(
                            "Repeated memory failures; Chat Studio is restarting "
                            "automatically under launchd supervision."
                        ) from exc
                    raise
            raise RuntimeError("local model load recovery exhausted")

        self._busy.set()
        try:
            return self._exec.submit(_load_with_recovery).result()
        finally:
            self._busy.clear()
            self._start_scheduled_restart()

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

            vision = is_vision_model(repo)

            if vision:
                # Vision-language models (e.g. Qwen3.5) load through mlx-vlm,
                # which returns (model, processor). The processor takes the
                # tokenizer slot; config is kept for apply_chat_template.
                try:
                    from mlx_vlm import load as vlm_load
                except Exception as e:
                    self._load_error = (
                        f"{repo} is a vision model but mlx-vlm isn't installed: {e}. "
                        f"Run Update / reinstall to pull mlx-vlm."
                    )
                    raise RuntimeError(self._load_error) from e
                try:
                    model, processor = vlm_load(repo)
                except Exception as e:
                    self._load_error = f"failed to load vision model {repo}: {e}"
                    raise RuntimeError(self._load_error) from e
                self._loaded = LoadedModel(
                    repo=repo, model=model, tokenizer=processor,
                    kind="vlm", config=getattr(model, "config", None),
                )
                self._load_error = None
                self._last_used = time.time()
                return {"repo": repo, "already_loaded": False, "kind": "vlm"}

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
        return bool(self.release_memory()["released"])

    def release_memory(self, reason: str = "manual") -> dict:
        """Drop the local model and clear MLX/Metal caches on the MLX worker."""
        if self._busy.is_set():
            raise RuntimeError("a model load or chat generation is active")
        return self._exec.submit(self._release_memory_sync, reason).result()

    def _release_memory_sync(self, reason: str) -> dict:
        if self._busy.is_set():
            raise RuntimeError("a model load or chat generation is active")
        actions = []
        repo = None
        with self._lock:
            if self._loaded is not None:
                repo = self._loaded.repo
                self._loaded = None
                actions.append("local model unloaded")
        import gc
        gc.collect()
        actions.append("Python garbage collection completed")
        try:
            import mlx.core as mx
            synchronize = getattr(mx, "synchronize", None)
            if callable(synchronize):
                synchronize()
            clear_cache = getattr(mx, "clear_cache", None)
            if callable(clear_cache):
                clear_cache()
                actions.append("MLX/Metal cache cleared")
        except Exception as exc:
            actions.append(f"MLX cache unavailable: {type(exc).__name__}")
        if reason.startswith("automatic:") and repo:
            self._last_auto_unload = {"repo": repo, "at": time.time(), "reason": reason}
        return {"released": bool(repo), "repo": repo, "actions": actions}

    @staticmethod
    def _service_installed() -> bool:
        root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        return os.path.isfile(os.path.join(root, "service", ".installed"))

    def _evict_after_memory_failure_sync(self) -> None:
        """Drop the active model from the dedicated MLX thread."""
        with self._lock:
            self._loaded = None
        import gc
        gc.collect()
        try:
            import mlx.core as mx
            synchronize = getattr(mx, "synchronize", None)
            if callable(synchronize):
                synchronize()
            clear_cache = getattr(mx, "clear_cache", None)
            if callable(clear_cache):
                clear_cache()
        except Exception:
            pass

    def _record_memory_failure_sync(self, exc: BaseException) -> None:
        self._consecutive_memory_failures += 1
        self._last_memory_event = {
            "time": time.time(),
            "error_type": type(exc).__name__,
            "snapshot": _memory_snapshot(),
        }
        self._evict_after_memory_failure_sync()
        print(
            f"[chat] verified memory failure {self._consecutive_memory_failures}/"
            f"{MEMORY_RESTART_FAILURES}; local model and MLX cache evicted",
            file=sys.stderr,
            flush=True,
        )
        if (
            self._consecutive_memory_failures < MEMORY_RESTART_FAILURES
            or self._restart_scheduled
        ):
            return
        if not self._service_installed():
            print(
                "[chat] repeated memory failures without startup-service "
                "supervision; keeping Chat Studio alive",
                file=sys.stderr,
                flush=True,
            )
            return
        self._restart_scheduled = True

    def _start_scheduled_restart(self) -> None:
        if not self._restart_scheduled or self._restart_timer_started:
            return
        self._restart_timer_started = True

        def _exit_for_launchd() -> None:
            print(
                "[chat] restarting after repeated memory failures; launchd "
                "KeepAlive will restore Chat Studio",
                file=sys.stderr,
                flush=True,
            )
            os._exit(75)

        timer = threading.Timer(0.75, _exit_for_launchd)
        timer.daemon = True
        timer.start()

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

    def build_prompt(self, repo: Optional[str], messages: list[dict], num_images: int = 0) -> tuple[LoadedModel, str]:
        loaded = self._require_loaded(repo)

        # ── Vision path: mlx-vlm builds the prompt from the messages list and
        #    places the image placeholder(s) on the last user turn itself. ──
        if loaded.kind == "vlm":
            from mlx_vlm import apply_chat_template as vlm_apply
            prompt = vlm_apply(loaded.tokenizer, loaded.config, messages, num_images=num_images)
            return loaded, prompt

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
        images: Optional[list] = None,
        usage_callback: Optional[Callable[[dict], None]] = None,
    ) -> Iterator[str]:
        """Yields text chunks as the model generates.

        The actual MLX generation runs on the manager's single worker thread —
        the SAME thread the model was loaded on — because MLX arrays are
        thread/stream-bound. Prompt building (tokenizer only, no GPU work) runs
        on the caller's thread; generated text is bridged back over a queue, so
        this stays a simple synchronous iterator for callers.

        `images` (data URLs / base64 / http URLs) are only used by vision
        models — text models ignore them."""
        self.touch()  # mark in-use so the idle auto-unload timer resets

        # Images only apply to the vision path; decode them to files so mlx-vlm
        # can read them (and remember which to delete afterwards).
        loaded_peek = self._require_loaded(repo)
        image_paths: list = []
        temp_paths: list = []
        if loaded_peek.kind == "vlm" and images:
            image_paths, temp_paths = _decode_images(images)

        loaded, prompt = self.build_prompt(repo, messages, num_images=len(image_paths))
        target_repo = getattr(loaded, "repo", None) or repo
        if not target_repo:
            raise RuntimeError("Local model identity is unavailable for safe recovery")
        del loaded_peek

        chunks: "queue.Queue" = queue.Queue()
        _DONE = object()

        def _run_attempt(current_loaded, current_prompt, state: dict):
            final_response = None
            if current_loaded.kind == "vlm":
                from mlx_vlm import stream_generate as vlm_stream
                for response in vlm_stream(
                    current_loaded.model,
                    current_loaded.tokenizer,
                    current_prompt,
                    image=(image_paths or None),
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                ):
                    final_response = response
                    text = getattr(response, "text", None)
                    if text:
                        state["emitted"] = True
                        chunks.put(("chunk", text))
                    if self._cancel.is_set():
                        break
                return final_response

            from mlx_lm import stream_generate
            from mlx_lm.sample_utils import make_sampler
            sampler = make_sampler(temp=temperature, top_p=top_p)
            for response in stream_generate(
                current_loaded.model,
                current_loaded.tokenizer,
                current_prompt,
                max_tokens=max_tokens,
                sampler=sampler,
            ):
                final_response = response
                text = getattr(response, "text", None)
                if text:
                    state["emitted"] = True
                    chunks.put(("chunk", text))
                if self._cancel.is_set():
                    break
            return final_response

        def _generate():
            nonlocal loaded, prompt
            # Reset cancellation on the worker right before generating, so a
            # second request arriving while this one is queued can't clear a
            # cancel meant for the generation that's actually running.
            self._cancel.clear()
            try:
                attempt = 0
                reload_required = False
                while True:
                    state = {"emitted": False}
                    retry = False
                    try:
                        if reload_required:
                            self._load_sync(target_repo)
                            loaded, prompt = self.build_prompt(
                                target_repo,
                                messages,
                                num_images=len(image_paths),
                            )
                            reload_required = False
                        final_response = _run_attempt(loaded, prompt, state)
                    except Exception as exc:
                        if _is_memory_failure(exc):
                            self._record_memory_failure_sync(exc)
                            retry = (
                                not state["emitted"]
                                and attempt < MEMORY_RETRY_LIMIT
                                and not self._restart_scheduled
                            )
                        else:
                            self._consecutive_memory_failures = 0
                        if not retry:
                            if self._restart_scheduled:
                                exc = RuntimeError(
                                    "Repeated memory failures; Chat Studio is "
                                    "restarting automatically under launchd supervision."
                                )
                            chunks.put(("error", exc))
                            return
                        # Drop the failed model reference before the next loop
                        # reloads it on this same MLX worker thread.
                        loaded = None
                        prompt = ""
                    if retry:
                        attempt += 1
                        reload_required = True
                        print(
                            "[chat] retrying once because memory failed before "
                            "the first output token",
                            file=sys.stderr,
                            flush=True,
                        )
                        continue

                    self._consecutive_memory_failures = 0
                    if final_response is not None and loaded.kind != "vlm":
                        prompt_tokens = getattr(final_response, "prompt_tokens", None)
                        completion_tokens = getattr(
                            final_response, "generation_tokens", None
                        )
                        if (
                            isinstance(prompt_tokens, int)
                            and not isinstance(prompt_tokens, bool)
                            and prompt_tokens >= 0
                            and isinstance(completion_tokens, int)
                            and not isinstance(completion_tokens, bool)
                            and completion_tokens >= 0
                        ):
                            chunks.put(("usage", {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "total_tokens": prompt_tokens + completion_tokens,
                                "finish_reason": str(
                                    getattr(final_response, "finish_reason", None) or "stop"
                                ),
                                "peak_memory": getattr(
                                    final_response, "peak_memory", None
                                ),
                            }))
                    chunks.put((_DONE, None))
                    return
            finally:
                for p in temp_paths:
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        self._busy.set()
        future = self._exec.submit(_generate)
        try:
            while True:
                kind, payload = chunks.get()
                if kind == "chunk":
                    yield payload
                elif kind == "usage":
                    if usage_callback is not None:
                        usage_callback(payload)
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
            try:
                future.result()
            finally:
                self.touch()
                self._busy.clear()
                self._start_scheduled_restart()

    def chat_once(
        self,
        repo: Optional[str],
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        top_p: float = 1.0,
        images: Optional[list] = None,
    ) -> str:
        """Non-streaming convenience wrapper — joins the full stream into one
        string. Used by callers that don't need token-by-token output."""
        return "".join(
            self.stream_chat(repo, messages, temperature, max_tokens, top_p, images)
        )

    def chat_once_with_usage(
        self,
        repo: Optional[str],
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        top_p: float = 1.0,
        images: Optional[list] = None,
    ) -> ChatGenerationResult:
        """Return a complete response only when MLX reports exact token usage."""
        evidence: dict = {}
        text = "".join(self.stream_chat(
            repo,
            messages,
            temperature,
            max_tokens,
            top_p,
            images,
            usage_callback=evidence.update,
        ))
        required = ("prompt_tokens", "completion_tokens", "total_tokens")
        if any(
            isinstance(evidence.get(field), bool)
            or not isinstance(evidence.get(field), int)
            or evidence[field] < 0
            for field in required
        ):
            raise RuntimeError("local generation did not return verified token usage")
        if evidence["total_tokens"] < evidence["prompt_tokens"] + evidence["completion_tokens"]:
            raise RuntimeError("local generation returned inconsistent token usage")
        return ChatGenerationResult(
            text=text,
            prompt_tokens=evidence["prompt_tokens"],
            completion_tokens=evidence["completion_tokens"],
            total_tokens=evidence["total_tokens"],
            finish_reason=str(evidence.get("finish_reason") or "stop"),
            peak_memory=(
                float(evidence["peak_memory"])
                if isinstance(evidence.get("peak_memory"), (int, float))
                else None
            ),
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
