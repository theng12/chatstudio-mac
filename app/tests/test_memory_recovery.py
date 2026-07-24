import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend import llm_engine


def _modules(stream_generate):
    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.stream_generate = stream_generate
    fake_sampling = types.ModuleType("mlx_lm.sample_utils")
    fake_sampling.make_sampler = lambda **_kwargs: object()
    return {
        "mlx_lm": fake_mlx_lm,
        "mlx_lm.sample_utils": fake_sampling,
    }


def _loaded():
    return SimpleNamespace(
        repo="org/model",
        kind="text",
        model=object(),
        tokenizer=object(),
    )


def test_memory_failure_before_first_token_reloads_and_retries_once():
    manager = llm_engine.LLMManager()
    loaded = _loaded()
    calls = 0

    def stream_generate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise MemoryError("MLX allocation failed")
        yield SimpleNamespace(
            text="recovered",
            prompt_tokens=2,
            generation_tokens=1,
            finish_reason="stop",
            peak_memory=1.0,
        )

    try:
        with (
            patch.object(manager, "_require_loaded", return_value=loaded),
            patch.object(
                manager, "build_prompt", return_value=(loaded, "prompt")
            ),
            patch.object(manager, "_load_sync", return_value={"repo": "org/model"}),
            patch.object(manager, "_evict_after_memory_failure_sync"),
            patch.object(manager, "_service_installed", return_value=False),
            patch.dict(sys.modules, _modules(stream_generate)),
        ):
            result = list(manager.stream_chat(
                "org/model", [{"role": "user", "content": "hello"}]
            ))
    finally:
        manager._exec.shutdown(wait=True)

    assert result == ["recovered"]
    assert calls == 2
    assert manager.memory_status()["consecutive_failures"] == 0
    assert manager.memory_status()["last_event"]["error_type"] == "MemoryError"
    assert "job_id" not in manager.memory_status()["last_event"]


def test_model_load_memory_failure_is_evicted_and_retried_once():
    manager = llm_engine.LLMManager()
    attempts = 0

    def load(_repo):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise MemoryError("cannot allocate memory")
        return {"repo": "org/model", "already_loaded": False}

    try:
        with (
            patch.object(manager, "_load_sync", side_effect=load),
            patch.object(manager, "_evict_after_memory_failure_sync"),
            patch.object(manager, "_service_installed", return_value=False),
        ):
            assert manager.load("org/model")["repo"] == "org/model"
    finally:
        manager._exec.shutdown(wait=True)

    assert attempts == 2
    assert manager.memory_status()["consecutive_failures"] == 0


def test_memory_failure_after_first_token_is_not_replayed():
    manager = llm_engine.LLMManager()
    loaded = _loaded()
    calls = 0

    def stream_generate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        yield SimpleNamespace(text="partial")
        raise MemoryError("out of memory")

    try:
        with (
            patch.object(manager, "_require_loaded", return_value=loaded),
            patch.object(
                manager, "build_prompt", return_value=(loaded, "prompt")
            ),
            patch.object(manager, "_evict_after_memory_failure_sync"),
            patch.object(manager, "_service_installed", return_value=False),
            patch.dict(sys.modules, _modules(stream_generate)),
        ):
            stream = manager.stream_chat(
                "org/model", [{"role": "user", "content": "hello"}]
            )
            assert next(stream) == "partial"
            with pytest.raises(RuntimeError, match="out of memory"):
                next(stream)
    finally:
        manager._exec.shutdown(wait=True)

    assert calls == 1
    assert manager.memory_status()["consecutive_failures"] == 1


def test_repeated_pre_token_memory_failure_requests_supervised_restart():
    manager = llm_engine.LLMManager()
    loaded = _loaded()
    calls = 0
    timers = []

    def stream_generate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise MemoryError()
        yield  # pragma: no cover

    class FakeTimer:
        def __init__(self, interval, callback):
            self.interval = interval
            self.callback = callback
            self.daemon = False

        def start(self):
            timers.append(self.interval)

    try:
        with (
            patch.object(manager, "_require_loaded", return_value=loaded),
            patch.object(
                manager, "build_prompt", return_value=(loaded, "prompt")
            ),
            patch.object(manager, "_load_sync", return_value={"repo": "org/model"}),
            patch.object(manager, "_evict_after_memory_failure_sync"),
            patch.object(manager, "_service_installed", return_value=True),
            patch.object(llm_engine.threading, "Timer", FakeTimer),
            patch.dict(sys.modules, _modules(stream_generate)),
        ):
            with pytest.raises(RuntimeError, match="restarting automatically"):
                list(manager.stream_chat(
                    "org/model", [{"role": "user", "content": "hello"}]
                ))
    finally:
        manager._exec.shutdown(wait=True)

    assert calls == 2
    assert manager.memory_status()["consecutive_failures"] == 2
    assert manager.memory_status()["restart_scheduled"] is True
    assert timers == [0.75]


def test_only_verified_allocator_errors_enter_recovery():
    assert llm_engine._is_memory_failure(MemoryError())
    assert llm_engine._is_memory_failure(RuntimeError("std::bad_alloc"))
    assert not llm_engine._is_memory_failure(
        RuntimeError("Hugging Face returned HTTP 401")
    )
    assert not llm_engine._is_memory_failure(RuntimeError("resource limit exceeded"))
