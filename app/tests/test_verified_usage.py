import asyncio
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import cache, llm_engine, main


class VerifiedUsageTests(unittest.TestCase):
    def test_snapshot_revision_requires_real_cached_weights(self):
        revision = "7f0dc925e0d0afb0322d96f9255cfddf2ba5636e"
        with patch.object(cache, "repo_cache_dir") as repo_cache:
            from tempfile import TemporaryDirectory
            from pathlib import Path

            with TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "refs").mkdir()
                (root / "refs" / "main").write_text(revision)
                snapshot = root / "snapshots" / revision
                snapshot.mkdir(parents=True)
                (snapshot / "model.safetensors").write_bytes(b"weight")
                repo_cache.return_value = root
                self.assertEqual(cache.snapshot_revision("org/model"), revision)

    def test_local_generation_captures_mlx_native_token_counts(self):
        manager = llm_engine.LLMManager()
        loaded = SimpleNamespace(kind="text", model=object(), tokenizer=object())
        responses = [
            SimpleNamespace(
                text="Hello",
                prompt_tokens=13,
                generation_tokens=1,
                finish_reason="stop",
                peak_memory=1.5,
            ),
            SimpleNamespace(
                text=" world",
                prompt_tokens=13,
                generation_tokens=2,
                finish_reason="stop",
                peak_memory=1.5,
            ),
        ]
        fake_mlx_lm = types.ModuleType("mlx_lm")
        fake_mlx_lm.stream_generate = lambda *args, **kwargs: iter(responses)
        fake_sampling = types.ModuleType("mlx_lm.sample_utils")
        fake_sampling.make_sampler = lambda **kwargs: object()
        try:
            with (
                patch.object(manager, "_require_loaded", return_value=loaded),
                patch.object(manager, "build_prompt", return_value=(loaded, "prompt")),
                patch.dict(sys.modules, {
                    "mlx_lm": fake_mlx_lm,
                    "mlx_lm.sample_utils": fake_sampling,
                }),
            ):
                result = manager.chat_once_with_usage(
                    "org/model", [{"role": "user", "content": "Hello"}]
                )
        finally:
            manager._exec.shutdown(wait=True)
        self.assertEqual(result.text, "Hello world")
        self.assertEqual(result.prompt_tokens, 13)
        self.assertEqual(result.completion_tokens, 2)
        self.assertEqual(result.total_tokens, 15)

    def test_openai_response_exposes_verified_usage_and_revision(self):
        revision = "7f0dc925e0d0afb0322d96f9255cfddf2ba5636e"
        result = llm_engine.ChatGenerationResult(
            text="Verified answer",
            prompt_tokens=9,
            completion_tokens=3,
            total_tokens=12,
            finish_reason="stop",
        )
        body = main.OpenAIChatCompletionsBody(
            model="org/model",
            messages=[main.ChatMessage(role="user", content="Hello")],
        )
        with (
            patch.object(llm_engine.manager, "ensure_loaded"),
            patch.object(llm_engine.manager, "chat_once_with_usage", return_value=result),
            patch.object(cache, "snapshot_revision", return_value=revision),
        ):
            payload = asyncio.run(main.openai_chat_completions(body))
        self.assertEqual(payload["usage"], {
            "prompt_tokens": 9,
            "completion_tokens": 3,
            "total_tokens": 12,
        })
        self.assertTrue(payload["usage_verified"])
        self.assertEqual(payload["model_revision"], revision)


if __name__ == "__main__":
    unittest.main()
