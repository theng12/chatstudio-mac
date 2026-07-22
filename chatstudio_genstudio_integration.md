# ChatStudio → GenStudio Integration Readiness

This document describes the maintained integration boundary for ChatStudio `1.24.1`.

GenStudio remains the public API, global job and attempt authority, routing and retry
authority, lease/fencing authority, and billing authority. ChatStudio is a local
executor: it loads a selected model, performs generation, streams execution output,
and reports execution evidence back to GenStudio.

## Executive assessment

ChatStudio is usable as a local LLM executor behind Studio Hub. Local non-streaming
OpenAI-compatible completions now return billing-grade tokenizer-native usage and an
immutable runtime revision. The API is not yet a durable or reconnectable streaming
execution contract.

The existing `/v1/chat/completions` endpoint is a useful transport starting point.
Production streaming integration still requires request-scoped cancellation,
structured-output behavior, explicit context metadata, durable execution status,
stable error envelopes, and a replay/resume protocol. GenStudio remains responsible
for global execution identity; Studio Hub maps that identity to this local executor.

## Release discipline

Every shipped ChatStudio change must increment the root numeric `VERSION` using the
existing semantic-versioning policy and add a matching top entry to `CHANGELOG.md`.
The changelog entry is the single source for the in-app **What's New** panel, so it
must say what changed, relevant limitations, and verification. This applies to
executor-contract changes as well as models, providers, dependencies, launchers, and
user-visible behavior.

## 1. Local model catalog

The curated catalog contains 46 local MLX entries in 14 families:

| Family | Count |
| --- | ---: |
| Llama | 5 |
| Qwen 2.5 | 9 |
| Qwen 3 | 2 |
| Qwen 3.5 Vision | 7 |
| Mistral | 3 |
| Ministral | 2 |
| Gemma 4 | 5 |
| Gemma 3 | 4 |
| Phi | 1 |
| Phi 4 | 2 |
| DeepSeek | 3 |
| Devstral | 1 |
| LFM | 1 |
| Nemotron | 1 |

The catalog covers:

- Llama 1B, 3B, 8B, Scout MoE, and 70B
- Qwen 0.5B through 32B and Qwen Coder variants
- Qwen3 4B and Qwen3 Coder 30B-A3B
- Qwen3.5 vision models from 0.8B through 122B-A10B
- Mistral 7B, Nemo 12B, and Small 24B
- Ministral 3B and 8B
- Gemma 3 1B, 4B, 12B, and 27B
- Gemma 4 E2B, E4B, 12B, 26B-A4B, and 31B
- Phi-3.5 Mini, Phi-4 Mini, and Phi-4 Mini Reasoning
- DeepSeek R1 Distill Qwen 7B and 14B, plus DeepSeek Coder V2 Lite
- Devstral Small 2 24B, LFM2.5 1.2B, and Nemotron3 Nano Omni 30B-A3B

Currently cached and reported loadable by the running service:

- `mlx-community/Llama-3.2-3B-Instruct-4bit`
- `mlx-community/gemma-3-4b-it-qat-4bit`
- `mlx-community/gemma-4-E2B-it-qat-4bit`

Remote provider models are separate from the local catalog. `/v1/models` may expose
models from configured OpenRouter, NVIDIA NIM, Groq, Cerebras, Gemini, OpenAI,
Anthropic, and other providers. Those listings are dynamic and are not immutable.

## 2. Immutable revisions

Downloads still follow each repository's configured Hugging Face revision, but a usable
cached snapshot resolves to an immutable commit. Cached non-vision catalog entries expose
that commit as `runtime_revision`, and successful local non-streaming `/v1` completions
return the same evidence as `model_revision`.

The three cached models currently have these local snapshot revisions:

| Model | Snapshot revision |
| --- | --- |
| `mlx-community/Llama-3.2-3B-Instruct-4bit` | `7f0dc925e0d0afb0322d96f9255cfddf2ba5636e` |
| `mlx-community/gemma-3-4b-it-qat-4bit` | `3d9ef289111449933c22761961f16a5df237ce2a` |
| `mlx-community/gemma-4-E2B-it-qat-4bit` | `42f62737af7a9fd8c1d55d79666c1a217be4e2e2` |

These hashes are local runtime evidence. Studio Hub can preserve the returned revision
with the assigned GenStudio attempt so GenStudio can prove which cached snapshot
generated a completed local result.

Current local non-streaming result evidence:

```json
{
  "model": "mlx-community/Llama-3.2-3B-Instruct-4bit",
  "model_revision": "7f0dc925e0d0afb0322d96f9255cfddf2ba5636e"
}
```

Streaming and cloud-provider results do not yet return equivalent immutable revision
evidence. GenStudio must qualify those paths separately rather than infer a revision.

## 3. Chat and completion API

### Native endpoint

```http
POST /api/chat/completions
```

Request fields:

```json
{
  "repo": "mlx-community/Llama-3.2-3B-Instruct-4bit",
  "messages": [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello"}
  ],
  "temperature": 0.7,
  "max_tokens": 1024,
  "top_p": 1.0,
  "stream": true,
  "images": []
}
```

Supported message roles are `system`, `user`, and `assistant`. Native non-streaming
responses are:

```json
{
  "repo": "…",
  "content": "…"
}
```

### OpenAI-compatible endpoint

```http
POST /v1/chat/completions
```

This uses `model` instead of `repo` and returns a basic OpenAI-compatible response.
Local models are loaded automatically when the requested model is cached.

```json
{
  "id": "chatcmpl-…",
  "object": "chat.completion",
  "created": 0,
  "model": "…",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "…"},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 456,
    "total_tokens": 579
  },
  "usage_verified": true,
  "model_revision": "7f0dc925e0d0afb0322d96f9255cfddf2ba5636e"
}
```

That verified envelope applies only to local, non-streaming completions. Cloud-provider
non-streaming responses still return unknown token counts, and streaming responses do
not yet emit final usage or revision evidence.

## 4. Streaming protocol

The native endpoint streams raw text chunks using `text/plain`. It has no event IDs,
sequence numbers, typed terminal event, usage event, or stable resume mechanism.

The OpenAI-compatible endpoint streams SSE using `text/event-stream`:

```text
data: {"id":"chatcmpl-…","object":"chat.completion.chunk",...}

data: [DONE]
```

Text is delivered through `choices[0].delta.content`. There are no token sequence
numbers or executor event IDs, so reconnecting cannot safely resume without possible
duplication. If Story Studio, Studio Hub, or GenStudio disconnects, it must treat the
stream as non-resumable; the current ChatStudio stream cannot be reattached or repaired
from a last-seen event. Retrying requires a new, globally controlled GenStudio attempt.

Uninterrupted/fallback mode also has an internal frontend sentinel named
`__CHATSTUDIO_META__`. This is not a stable external integration protocol.

## 5. Structured JSON

Structured JSON is not implemented. There is no support for:

- `response_format`
- JSON mode
- JSON Schema
- constrained decoding
- schema validation
- structured-output error reporting

The request model does not define these fields, and unsupported fields are not
explicitly rejected. A client may therefore send `response_format` and receive a
normal unconstrained response.

GenStudio must either receive a real structured-output implementation or a clear
capability error such as:

```json
{
  "error": {
    "code": "structured_output_unsupported",
    "message": "Structured JSON is not supported for the selected executor/model."
  }
}
```

## 6. Token usage

Local, non-streaming `/v1/chat/completions` now provides verified token usage:

- Prompt and completion counts come from the loaded MLX tokenizer/runtime result.
- `usage_verified: true` distinguishes this evidence from UI estimates.
- `model_revision` identifies the immutable cached snapshot used.
- Missing native usage evidence fails the local non-streaming contract instead of being
  silently estimated.

The UI still uses approximate display metrics, the native endpoint does not return the
same evidence envelope, cloud-provider usage remains unknown, and streaming has no final
usage event. GenStudio may use verified local non-streaming evidence but must not bill
from UI estimates or null cloud/streaming usage.

```json
{
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 456,
    "total_tokens": 579
  }
}
```

For future streaming qualification, usage and runtime revision should appear in a typed,
durable terminal event that can be replayed after reconnect.

## 7. Context limits

Current request-level limits are:

- maximum 200 messages
- maximum 1,000,000 characters per message
- maximum output tokens: 32,768
- no total prompt-token limit
- no model-aware context validation

The catalog contains family-level context notes, but ChatStudio does not consistently
derive a true context limit from each model revision. It builds prompts through the
loaded tokenizer but does not expose prompt-token counts or reject requests that exceed
the model's actual context window.

Cached inspection found:

- Llama 3.2 3B: `max_position_embeddings = 131072`
- Gemma 3 4B: no directly readable context value in the inspected config
- Gemma 4 E2B: no directly readable context value in the inspected config

GenStudio needs a live, model-specific capability response:

```json
{
  "context": {
    "max_input_tokens": 131072,
    "max_output_tokens": 32768,
    "max_total_tokens": 131072
  }
}
```

## 8. Cancellation

`POST /api/chat/cancel` sets a global cancellation event. Local MLX generation checks
it between generated tokens. The native streaming generator also handles
`GeneratorExit` when its consumer disconnects.

This is adequate for the local UI but is not a GenStudio-grade cancellation contract:

- cancellation is global rather than execution-scoped
- there is no request or attempt ID
- cancellation is token-boundary based
- there is no durable execution state

The `/v1` streaming handler starts a background producer thread and does not expose a
request-scoped cancellation ID or a clear disconnect-to-worker cancellation path.
GenStudio should use an explicit execution cancellation endpoint:

```http
POST /api/executions/{execution_id}/cancel
```

The response should identify whether the execution was queued, loading, running,
cancelling, cancelled, or already complete.

## 9. Tool/function calling

Tool calling is not implemented. There is no support for:

- `tools`
- `tool_choice`
- `functions`
- `function_call`
- tool-call deltas
- tool result messages
- tool permission boundaries

Model-family marketing claims about tool use must not be treated as ChatStudio
capabilities.

## 10. Model loading and memory

ChatStudio uses `mlx-lm` for text models and `mlx-vlm` for vision-language models.
All MLX operations run through one dedicated worker thread, and at most one local
model is held in memory at a time. Loading another model unloads the previous model.

Memory features include:

- Performance mode: keep loaded
- Balanced mode: unload after 10 minutes
- Memory Saver: unload after 2 minutes
- Immediate mode: unload after each completed local response
- explicit Release Memory / Unload Model

Catalog memory floors range from 8 GB to 96 GB unified memory. MoE entries account for
the full checkpoint footprint rather than only active experts.

The catalog exposes parameter count, quantization, download size, minimum memory,
recommended hardware, specialty flags, and—when a non-vision model is cached—its
immutable `runtime_revision`, verified-usage capability, and output-token limit. It does
not expose exact context, tokenizer/processor hashes, actual memory used, load duration,
or generation speed.

GenStudio should treat catalog memory values as advisory and consult live executor
readiness before dispatch.

## 11. Studio Hub compatibility

ChatStudio exposes `GET /api/capabilities` with:

```json
{
  "schema_version": 1,
  "studio": {"modality": "chat", "title": "Chat Studio KH", "app_version": "1.24.1"},
  "auth": {"mode": "fleet_token", "header": "X-Studio-Token", "loopback_exempt": true},
  "operations": ["chat", "vision", "openai_compatible"],
  "catalog_endpoint": "/api/catalog",
  "diagnostics_endpoint": "/api/chat/diagnostics",
  "update": {"script": "update.js", "supports_drain": true}
}
```

Studio Hub documents a synchronous gateway:

```http
POST /studio/chat/v1/chat/completions
```

The gateway proxies requests and streams SSE responses. This is compatible with basic
GenStudio text generation. ChatStudio intentionally does not claim global ownership or
independently generate/persist:

- `genstudio_job_id`
- `genstudio_attempt_id`
- `idempotency_key`
- `fencing_token`
- executor lease information
- billing metadata

For local non-streaming completions, ChatStudio returns `model_revision` as execution
evidence. It does not accept an expected revision or reject a revision mismatch before
generation yet.

Studio Hub and GenStudio already establish the correct authority boundary: GenStudio
owns global jobs, attempts, routing, retries, leases, fencing, and billing. ChatStudio
should remain a local executor and report only execution evidence.

## 12. Error behavior

Native streaming errors can be inserted into an otherwise successful `200 OK` text
stream as:

```text
[error] RuntimeError: ...
```

OpenAI streaming errors are sent as an SSE chunk with `finish_reason: "error"` and an
`error` field, followed by `[DONE]`. There are no stable machine-readable error codes.

Common non-stream status behavior includes:

- `409`: local model missing, not cached, or failed to load
- `401`: missing provider credential
- `403`: paid provider model not enabled
- `502`: upstream provider/API failure

GenStudio needs stable error codes, explicit executor state, and no error text mixed
into assistant content.

## 13. Required GenStudio contract changes

Before production streaming integration, add:

1. Request-scoped cancellation.
2. Model-specific context limits and preflight validation.
3. Structured JSON capability and enforcement, or explicit unsupported errors.
4. Stable error codes and typed terminal states.
5. Stream event IDs and a defined reconnect/replay policy.
6. Client-disconnect cancellation for the exact local execution.
7. Verified usage and immutable revision in the streaming terminal event.
8. Durable executor status for queued, loading, running, cancelling, failed,
    cancelled, and completed states.

GenStudio job IDs, attempt IDs, idempotency, fencing, billing, and global retry decisions
remain GenStudio responsibilities. Studio Hub may carry an explicitly assigned attempt
to ChatStudio and retain local execution evidence, but ChatStudio must not become a
second global job authority.

Recommended result envelope:

```json
{
  "execution_id": "exec_123",
  "genstudio_job_id": "job_123",
  "genstudio_attempt_id": "attempt_2",
  "status": "completed",
  "model": "mlx-community/Llama-3.2-3B-Instruct-4bit",
  "model_revision": "7f0dc925e0d0afb0322d96f9255cfddf2ba5636e",
  "output": {"role": "assistant", "content": "…"},
  "usage": {"prompt_tokens": 123, "completion_tokens": 456, "total_tokens": 579},
  "timing": {"queued_ms": 20, "load_ms": 0, "first_token_ms": 420, "total_ms": 6300},
  "executor": {
    "studio": "chatstudio",
    "app_version": "1.24.1",
    "backend": "mlx-lm"
  }
}
```

## Readiness summary

| Area | Status |
| --- | --- |
| Local model execution | Ready |
| Basic OpenAI transport | Partially ready |
| SSE streaming | Partially ready |
| Immutable model identity | Ready for cached local non-streaming results |
| Billing-grade usage | Ready for local non-streaming results |
| Structured JSON | Not supported |
| Tool calling | Not supported |
| Context enforcement | Not ready |
| Explicit cancellation | Partially ready |
| GenStudio job identity | Owned by GenStudio/Studio Hub adapter |
| Studio Hub synchronous routing | Compatible |
| Durable GenStudio execution | Not ready |
| Local-executor authority boundary | Architecturally appropriate |
