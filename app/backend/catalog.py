"""
Static catalog of MLX-ready instruction-tuned chat models for Chat Studio (Mac).

Every entry is a pre-quantized, already-MLX-converted repo from the
`mlx-community` Hugging Face org — no conversion step needed, `mlx_lm.load`
can load these directly. Each entry describes the HF repo plus metadata the UI
uses: verified download size, hardware floor, family grouping, and a
"best for" note.

Sizing note: `size_gb` values are verified against the current Hugging Face
repository file metadata in the release audit. They are decimal GB totals for
the complete repository snapshot, including tokenizer, processor, config, and
all weight shards. The live `/api/cache` and `/api/downloads` endpoints report
the actual bytes on this machine.

MoE (Mixture-of-Experts) models load ALL experts into memory — the total
param count determines the RAM floor even though only a subset activates per
token. Their size_gb is the verified repository total; their memory floor
reflects the full checkpoint, not only the active experts.

How `min_unified_memory_gb` is derived
--------------------------------------
It is a *machine* RAM tier, but the number that actually constrains a load is
the GPU working set, not total RAM. macOS gives Metal roughly 66.67% of unified
memory by default (`iogpu.wired_limit_mb = 0`); a 16 GB M4 Mac mini reports a
"maximum recommended working set size" of 10922 MB, which is exactly two thirds
of 16 GiB. So the usable budget in decimal GB is about `tier * 0.716`:

    8 GB → 5.7    16 GB → 11.4    24 GB → 17.2
    32 GB → 22.9    36 GB → 25.8   48 GB → 34.4    64 GB → 45.8    96 GB → 68.7

Entries corrected in 1.25.3 use:

    weights (size_gb) + KV cache at 32K context + 0.8 GB runtime overhead
        <= 0.6667 * tier

The KV term is computed from each repo's own `config.json` — layer count, KV
head count, head dim, and the sliding/full/linear attention pattern — at fp16,
which is what this app uses (the engine sets no `kv_bits` and no `max_kv_size`,
so the cache is unquantized and unbounded). It varies enormously between
architectures at the same parameter count: Gemma 4 interleaves short-window
sliding layers with a few global ones and costs 1.6-2.5 GB at 32K, while
Phi-3.5-mini has no grouped-query attention at all and costs 12.9 GB.

Older entries predate this derivation and were sized from the file size alone,
against *total* RAM rather than the GPU budget — so they read optimistic. They
are left as-is pending measurement on real hardware; see CHANGELOG 1.25.3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Family:
    id: str
    label: str
    summary: str
    how_to_use: str
    context_note: Optional[str] = None


FAMILIES: dict[str, Family] = {
    "llama": Family(
        id="llama",
        label="Llama",
        summary=(
            "Meta's Llama 3.x/4 instruction-tuned chat models, quantized to MLX "
            "by mlx-community. Strong general-purpose assistants with broad "
            "community tooling support. Includes dense models from 1B to 70B "
            "and the MoE Llama 4 Scout."
        ),
        how_to_use=(
            "Load a Llama model in the Chat tab and talk to it like any chat "
            "assistant. The 3.2 3B is the recommended starter — fast, "
            "small, and good enough for most everyday tasks. Step up to 8B "
            "for better reasoning, or Scout / 70B on high-RAM Macs."
        ),
        context_note=(
            "Llama models support long context windows (128K for 3.x, up to 1M "
            "for 4 Scout); actual usable context depends on available unified "
            "memory. Licence check: every Llama here is under the Llama "
            "Community Licence, not an open-source licence. Commercial use is "
            "allowed below 700 million monthly active users, and any product "
            "built on one must be attributed with \"Built with Llama\". Pick a "
            "Qwen, Mistral, or Gemma model instead if you would rather not "
            "carry that obligation."
        ),
    ),
    "qwen": Family(
        id="qwen",
        label="Qwen",
        summary=(
            "Alibaba's Qwen2.5 instruction-tuned chat models, quantized to MLX "
            "by mlx-community. Spans from a tiny 0.5B to a dense 32B, with "
            "dedicated Coder variants for programming tasks. Strong multilingual "
            "support."
        ),
        how_to_use=(
            "Pick the size that fits your Mac. 0.5B-3B for 8 GB machines, "
            "7B for 16 GB, 14B for 24 GB+, 32B for 32 GB+. Coder variants "
            "are fine-tuned specifically for code generation and debugging."
        ),
        context_note="Qwen2.5 models support up to a 128K context window upstream (32K native on some sizes); actual usable context here depends on available unified memory.",
    ),
    "qwen3": Family(
        id="qwen3",
        label="Qwen3",
        summary=(
            "Alibaba's Qwen3 generation (mid-2025) — the successor to Qwen2.5 "
            "with improved reasoning, tool use, and multilingual performance. "
            "Quantized to MLX by mlx-community. Includes dense and MoE variants."
        ),
        how_to_use=(
            "The 4B is a strong general-purpose model that fits any Mac. "
            "The Coder 30B-A3B MoE activates only ~3B params per token for "
            "fast code generation while keeping 30B of knowledge in memory."
        ),
        context_note="Qwen3 supports up to a 128K context window upstream; actual usable context depends on available unified memory.",
    ),
    "qwen3.5": Family(
        id="qwen3.5",
        label="Qwen3.5 (Vision)",
        summary=(
            "Alibaba's Qwen3.5 generation — a unified vision-language family "
            "(text + image understanding), quantized to MLX by mlx-community. "
            "Unlike the text-only Qwen families, these load through mlx-vlm and "
            "can read attached images. Dense sizes 0.8B–27B plus A3B / A10B MoE "
            "variants."
        ),
        how_to_use=(
            "Load one and chat as usual — you can also attach an image with the "
            "📎 button and ask about it. The 9B is the recommended all-rounder; "
            "the 4B fits any Mac; 35B-A3B and 122B-A10B are MoE models for "
            "high-RAM machines. Needs mlx-vlm (installed with the app) — run "
            "Update if a model reports the vision engine is missing."
        ),
        context_note="Qwen3.5 supports up to a 256K context window upstream; actual usable context depends on available unified memory. Image input requires mlx-vlm.",
    ),
    "qwen3.8": Family(
        id="qwen3.8",
        label="Qwen3.8",
        summary=(
            "Alibaba's Qwen3.8 (August 2026) — the newest Qwen generation, "
            "Apache-2.0 and quantized to MLX by mlx-community. Built on the "
            "Qwen3.5 architecture with three linear-attention layers per full "
            "attention layer, which keeps working memory low even at long "
            "context."
        ),
        how_to_use=(
            "Only the dense 27B is published at a size worth running locally. "
            "It needs a 32 GB Mac; on 24 GB, Gemma 4 26B A4B is the better fit "
            "for the same kind of work."
        ),
        context_note="Qwen3.8 supports up to a 256K context window upstream; actual usable context depends on available unified memory.",
    ),
    "mistral": Family(
        id="mistral",
        label="Mistral",
        summary=(
            "Mistral AI's family of instruction-tuned models, quantized to MLX "
            "by mlx-community. Apache-2.0 licensed, fast, and available in "
            "multiple sizes from 7B to 24B. Includes Mistral Nemo (12B, "
            "co-developed with NVIDIA)."
        ),
        how_to_use=(
            "The 7B v0.3 is the classic lightweight general assistant. "
            "Nemo 12B is a strong mid-size step-up. Small 3.1 24B is "
            "for high-RAM Macs needing top-tier quality."
        ),
        context_note="Context windows vary by model: 32K for 7B v0.3, 128K for Nemo and Small 3.1.",
    ),
    "ministral": Family(
        id="ministral",
        label="Ministral",
        summary=(
            "Mistral AI's Ministral 3 series (late 2025) — a next-generation "
            "architecture focused on efficiency and reasoning. Available in 3B "
            "and 8B sizes, both quantized to MLX by mlx-community."
        ),
        how_to_use=(
            "The 3B is excellent for 8 GB Macs — faster and more capable "
            "than similarly-sized models. The 8B competes with 7B-class "
            "models while being more efficient."
        ),
        context_note="Ministral 3 supports up to a 128K context window upstream; actual usable context depends on available unified memory.",
    ),
    "gemma4": Family(
        id="gemma4",
        label="Gemma 4",
        summary=(
            "Google's Gemma 4 (April 2026) — their most capable open-weight "
            "models to date, and the most memory-frugal family here at long "
            "context: five short-window sliding layers per global layer means "
            "the working memory barely grows as the conversation does. Includes "
            "MatFormer 'E' variants (E2B / E4B), a 26B Mixture-of-Experts that "
            "activates only ~4B params per token, and a dense 31B. Each size "
            "ships twice: a plain 4-bit build and a larger QAT build."
        ),
        how_to_use=(
            "Two builds per size. The plain 4-bit is uniformly quantized and "
            "smaller — pick it to fit a size onto a machine that couldn't "
            "otherwise hold it. The QAT build keeps its quantization-sensitive "
            "layers at 8-bit, so it is 1.2-1.6x larger but closer to "
            "full-precision quality — pick it when the size already fits with "
            "room to spare. Start at E2B/E4B, step up to 12B, then the 26B MoE. "
            "Pick a size whose fit chip is green for your machine."
        ),
        context_note=(
            "Gemma 4 supports very long context upstream (up to 256K on some "
            "variants); usable context here depends on available unified memory. "
            "These are multimodal models, but Chat Studio drives them as "
            "text-only chat — image/audio input is not exposed in this UI."
        ),
    ),
    "gemma3": Family(
        id="gemma3",
        label="Gemma 3",
        summary=(
            "Google's Gemma 3 (2025) open models, quantized with QAT "
            "(quantization-aware training) for near-bf16 quality at 4-bit. "
            "Sizes span a tiny 1B up to a heavyweight 27B, so there's a fit for "
            "everything from an 8 GB MacBook Air to a 64 GB Studio."
        ),
        how_to_use=(
            "The 4B is the sweet spot for most Macs — fast and capable. Drop to "
            "1B on very memory-constrained machines, or step up to 12B / 27B "
            "for stronger reasoning when you have the unified memory to spare."
        ),
        context_note=(
            "Gemma 3 supports a 128K context window upstream; usable context "
            "here depends on available unified memory. Multimodal upstream, but "
            "used here for text chat only."
        ),
    ),
    "phi": Family(
        id="phi",
        label="Phi",
        summary=(
            "Microsoft's Phi-3.5-mini instruction-tuned chat model, quantized "
            "to MLX by mlx-community. Small footprint with surprisingly "
            "capable reasoning for its size."
        ),
        how_to_use=(
            "Pick this when you want a tiny, fast model with better reasoning "
            "than its size would suggest — good for quick Q&A and lightweight "
            "assistant tasks on memory-constrained Macs."
        ),
        context_note="Phi-3.5-mini supports a 128K context window upstream; actual usable context here depends on available unified memory.",
    ),
    "phi4": Family(
        id="phi4",
        label="Phi-4",
        summary=(
            "Microsoft's Phi-4 generation — compact models with strong "
            "reasoning for their size, quantized to MLX by mlx-community. "
            "Includes the Mini instruct and a dedicated reasoning variant."
        ),
        how_to_use=(
            "Phi-4 Mini is a strong general-purpose 3.8B model. The "
            "Reasoning variant is fine-tuned for step-by-step thinking "
            "on math, logic, and planning tasks."
        ),
        context_note="Phi-4 Mini supports up to 128K context upstream; actual usable context depends on available unified memory.",
    ),
    "deepseek": Family(
        id="deepseek",
        label="DeepSeek",
        summary=(
            "DeepSeek's reasoning-distilled and code-specialized models, "
            "quantized to MLX by mlx-community. Includes R1 distill checkpoints "
            "trained to show step-by-step reasoning, and a dedicated coder "
            "model for programming tasks."
        ),
        how_to_use=(
            "R1 Distill models for math, logic, and multi-step planning — "
            "they reason out loud before answering. The Coder V2 Lite is "
            "fine-tuned for code generation and completion. 7B fits 12 GB; "
            "14B needs 16 GB+."
        ),
        context_note="R1 Distill models show their reasoning chain before the final answer, which makes responses longer but more verifiable.",
    ),
    "devstral": Family(
        id="devstral",
        label="Devstral",
        summary=(
            "Devstral Small 2 (late 2025) — a 24B instruction-tuned model "
            "from Mistral AI, quantized to MLX by mlx-community. Apache-2.0. "
            "Strong general-purpose quality competitive with much larger models."
        ),
        how_to_use=(
            "A great pick for 24 GB+ Macs when you want near-frontier "
            "quality without the massive footprint of a 70B. Slower to "
            "load and generate than smaller models, but output quality is "
            "noticeably better."
        ),
        context_note="Devstral Small 2 supports a 128K context window upstream; actual usable context depends on available unified memory.",
    ),
    "lfm": Family(
        id="lfm",
        label="LFM",
        summary=(
            "LFM 2.5 (Liquid Foundation Models, from Liquid AI) — a tiny 1.2B "
            "instruction-tuned model that punches well above its weight class, "
            "quantized to MLX by mlx-community."
        ),
        how_to_use=(
            "An excellent tiny model for 8 GB Macs. Nearly instant to load, "
            "fast generation, and surprisingly capable reasoning for its "
            "size. A great alternative to Gemma 3 1B and Llama 3.2 1B."
        ),
        context_note=(
            "Licence check: released under the LFM Open Licence v1.0, not "
            "Apache-2.0. Commercial use is free only below roughly $10M annual "
            "revenue; above that Liquid AI requires a separate agreement. "
            "Review it before shipping this model inside a paid product."
        ),
    ),
    "nemotron": Family(
        id="nemotron",
        label="Nemotron",
        summary=(
            "NVIDIA's Nemotron 3 Nano family — compact instruction models "
            "built for high-throughput production work rather than "
            "conversation. Includes a dense 4B, a 30B MoE that activates only "
            "~3B params per token, and an Omni reasoning variant that thinks "
            "step by step. Quantized to MLX by mlx-community."
        ),
        how_to_use=(
            "Pick the plain 4B or 30B-A3B for mechanical bulk work — "
            "extraction, tagging, classification, metadata — where you want a "
            "short answer and no visible deliberation. Pick the Omni Reasoning "
            "variant only when you actually want the reasoning chain, on math, "
            "science, or multi-step planning; it is slower because it writes "
            "its thinking out."
        ),
        context_note="Released under the NVIDIA Open Model licence — commercial use is permitted. The MoE variants keep all 30B in memory while activating ~3B per token. 128K context upstream.",
    ),
}


@dataclass(frozen=True)
class ModelEntry:
    repo: str
    label: str
    family: str
    size_gb: float
    gated: bool = False
    min_unified_memory_gb: int = 8
    recommended_hardware: str = ""
    params_b: float = 0.0
    quant: str = "4bit"
    best_for: str = ""
    is_starter: bool = False
    is_coder: bool = False
    is_reasoning: bool = False
    is_vision: bool = False        # vision-language model — loads via mlx-vlm, accepts images


CATALOG: tuple[ModelEntry, ...] = (
    # ──────────── Llama ────────────
    ModelEntry(
        repo="mlx-community/Llama-3.2-3B-Instruct-4bit",
        label="Llama 3.2 3B Instruct (4-bit) — recommended starter",
        family="llama",
        size_gb=1.825,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Fast load, fast generation.",
        params_b=3,
        quant="4bit",
        is_starter=True,
        best_for="The recommended starter model — small, fast, and good enough for everyday chat, summarization, and quick Q&A. Load this first to confirm everything works before trying bigger models.",
    ),
    ModelEntry(
        repo="mlx-community/Llama-3.2-1B-Instruct-4bit",
        label="Llama 3.2 1B Instruct (4-bit)",
        family="llama",
        size_gb=0.713,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Tiny and very fast.",
        params_b=1,
        quant="4bit",
        best_for="The lightest Llama — even faster than the 3B. Good for quick drafts, low-latency tasks, and running on the most memory-constrained Macs.",
    ),
    ModelEntry(
        repo="mlx-community/Meta-Llama-3.1-8B-Instruct-4bit",
        label="Llama 3.1 8B Instruct (4-bit)",
        family="llama",
        size_gb=4.527,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended for comfortable headroom.",
        params_b=8,
        quant="4bit",
        best_for="Noticeably better reasoning and instruction-following than the 3B model, still comfortably fast on Apple Silicon. The default step-up once you outgrow 3B.",
    ),
    ModelEntry(
        repo="mlx-community/Llama-4-Scout-17B-16E-Instruct-4bit",
        label="Llama 4 Scout 17B-16E MoE Instruct (4-bit)",
        family="llama",
        size_gb=61.144,
        is_vision=True,
        min_unified_memory_gb=96,
        recommended_hardware="96 GB+ unified memory. Multimodal MoE: the full checkpoint stays in memory even though only a subset of experts activates per token.",
        params_b=17,
        quant="4bit",
        best_for="Meta's latest MoE model — strong quality at a reasonable footprint. Generates faster than a dense 17B would because only ~4B experts fire per token.",
    ),
    ModelEntry(
        repo="mlx-community/Llama-3.3-70B-Instruct-4bit",
        label="Llama 3.3 70B Instruct (4-bit)",
        family="llama",
        size_gb=39.706,
        min_unified_memory_gb=64,
        recommended_hardware="64 GB. Its 39.7 GB of weights overrun a 48 GB Mac's ~34.4 GB GPU budget; even on 64 GB, keep context near 16K because full attention on 80 layers costs ~10.7 GB at 32K.",
        params_b=70,
        quant="4bit",
        best_for="The most capable Llama — top-tier reasoning, writing, and instruction-following. Reserve for high-RAM Macs (48 GB+).",
    ),

    # ──────────── Qwen ────────────
    ModelEntry(
        repo="mlx-community/Qwen2.5-0.5B-Instruct-4bit",
        label="Qwen2.5 0.5B Instruct (4-bit)",
        family="qwen",
        size_gb=0.290,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac. The smallest Qwen.",
        params_b=0.5,
        quant="4bit",
        best_for="The tiniest Qwen — near-instant load, fast generation. Good for quick Q&A on memory-constrained Macs where every MB counts.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
        label="Qwen2.5 1.5B Instruct (4-bit)",
        family="qwen",
        size_gb=0.880,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=1.5,
        quant="4bit",
        best_for="A small but capable Qwen — noticeably better than 0.5B while still instant to load. Good for fast, lightweight chat.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-3B-Instruct-4bit",
        label="Qwen2.5 3B Instruct (4-bit)",
        family="qwen",
        size_gb=1.748,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Fast load and generation.",
        params_b=3,
        quant="4bit",
        best_for="LICENCE WARNING — this is the one model here you cannot sell against: unlike the rest of Qwen2.5, the 3B is released under the Qwen Research Licence, which is non-commercial. Use Qwen2.5 1.5B, Gemma 4 E2B, or Llama 3.2 3B for anything commercial. Otherwise: a capable tiny Qwen with strong multilingual coverage.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-7B-Instruct-4bit",
        label="Qwen2.5 7B Instruct (4-bit)",
        family="qwen",
        size_gb=4.296,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended.",
        params_b=7,
        quant="4bit",
        best_for="Strong general-purpose assistant with good multilingual support. A solid alternative to Llama 3.1 8B at a similar size.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-14B-Instruct-4bit",
        label="Qwen2.5 14B Instruct (4-bit)",
        family="qwen",
        size_gb=8.321,
        min_unified_memory_gb=16,
        recommended_hardware="M2 Pro / M3 16 GB+ recommended for comfortable headroom.",
        params_b=14,
        quant="4bit",
        best_for="Rich reasoning in a mid-size package. Pick this when 7B-class models aren't giving you enough depth and you have 16 GB+.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-32B-Instruct-4bit",
        label="Qwen2.5 32B Instruct (4-bit)",
        family="qwen",
        size_gb=18.443,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB+ unified memory recommended.",
        params_b=32,
        quant="4bit",
        best_for="The largest dense Qwen2.5 — near-frontier quality for complex reasoning, writing, and analysis. For 32 GB+ Macs.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit",
        label="Qwen2.5 Coder 1.5B Instruct (4-bit)",
        family="qwen",
        size_gb=0.880,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=1.5,
        quant="4bit",
        is_coder=True,
        best_for="A tiny code-specialized model — fine-tuned for programming tasks. Fits any Mac and is surprisingly capable for its size on simple coding questions.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        label="Qwen2.5 Coder 7B Instruct (4-bit)",
        family="qwen",
        size_gb=4.296,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended.",
        params_b=7,
        quant="4bit",
        is_coder=True,
        best_for="Dedicated code model — fine-tuned for programming tasks (completion, refactoring, debugging, explaining code). Pick this over the plain Qwen2.5 7B for anything code-related.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-Coder-14B-Instruct-4bit",
        label="Qwen2.5 Coder 14B Instruct (4-bit)",
        family="qwen",
        size_gb=8.321,
        min_unified_memory_gb=16,
        recommended_hardware="M2 Pro / M3 16 GB+ recommended.",
        params_b=14,
        quant="4bit",
        is_coder=True,
        best_for="The most capable Qwen code model — significantly better reasoning on complex programming tasks than the 7B Coder. For 16 GB+ Macs.",
    ),

    # ──────────── Qwen3 ────────────
    ModelEntry(
        repo="mlx-community/Qwen3-4B-Instruct-2507-4bit",
        label="Qwen3 4B Instruct (4-bit)",
        family="qwen3",
        size_gb=2.279,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=4,
        quant="4bit",
        best_for="The new Qwen3 generation — improved reasoning over Qwen2.5 at the same size. A great everyday assistant that fits any Mac.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit",
        label="Qwen3 Coder 30B-A3B MoE Instruct (4-bit)",
        family="qwen3",
        size_gb=17.197,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB. Its 17.2 GB of weights exactly fill a 24 GB Mac's GPU budget, leaving nothing for context. MoE: all 30B in memory, ~3B active per token.",
        params_b=30,
        quant="4bit",
        is_coder=True,
        best_for="A fast MoE code model — activates only ~3B params per token for quick generation while keeping 30B of knowledge loaded. Top-tier code quality, but it needs 32 GB; on smaller Macs use Qwen2.5 Coder 14B.",
    ),

    # ──────────── Qwen3.5 (Vision-Language) ────────────
    # Unified VL models — load via mlx-vlm (is_vision=True), accept image input.
    # -MLX-4bit naming for the small dense sizes, plain -4bit for the larger MoE.
    ModelEntry(
        repo="mlx-community/Qwen3.5-4B-MLX-4bit",
        label="Qwen3.5 4B (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=3.061,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Fits everywhere.",
        params_b=4,
        quant="4bit",
        is_vision=True,
        best_for="The lightweight Qwen3.5 vision model — fits any Mac and still reads images. Good starter to confirm the vision engine works before pulling a bigger one.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3.5-9B-MLX-4bit",
        label="Qwen3.5 9B (Vision, MLX 4-bit) — recommended",
        family="qwen3.5",
        size_gb=5.977,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended (weights ~6 GB + vision encoder).",
        params_b=9,
        quant="4bit",
        is_vision=True,
        best_for="The recommended Qwen3.5 pick — the best quality/size balance for image understanding + chat on a 16 GB Mac.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3.5-0.8B-MLX-4bit",
        label="Qwen3.5 0.8B (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=0.652,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac. Tiny and fast.",
        params_b=0.8,
        quant="4bit",
        is_vision=True,
        best_for="The smallest vision model — fast, low-memory image captioning and quick multimodal Q&A on any Mac.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3.5-2B-MLX-4bit",
        label="Qwen3.5 2B (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=1.749,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=2,
        quant="4bit",
        is_vision=True,
        best_for="A small step up from 0.8B with better image reasoning, still comfortable on 8 GB Macs.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3.5-27B-4bit",
        label="Qwen3.5 27B (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=16.081,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB. 16.1 GB of weights plus ~2.2 GB at 32K overruns a 24 GB Mac's ~17.2 GB GPU budget.",
        params_b=27,
        quant="4bit",
        is_vision=True,
        best_for="The dense 27B — noticeably stronger image + text reasoning than the 9B. Needs 32 GB; on a 24 GB Mac use Gemma 4 26B A4B instead.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3.5-35B-A3B-4bit",
        label="Qwen3.5 35B-A3B MoE (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=20.419,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB+ recommended. MoE: ~3B params active per token for fast generation.",
        params_b=35,
        quant="4bit",
        is_vision=True,
        best_for="MoE vision model — 35B of knowledge in memory but only ~3B active per token, so it generates faster than a dense 35B. Great quality/speed on 32 GB+ Macs.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3.5-122B-A10B-4bit",
        label="Qwen3.5 122B-A10B MoE (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=69.621,
        min_unified_memory_gb=128,
        recommended_hardware="128 GB. Its 69.6 GB of weights overrun a 96 GB Mac's ~68.7 GB GPU budget. ~10B params active per token.",
        params_b=122,
        quant="4bit",
        is_vision=True,
        best_for="The flagship Qwen3.5 vision MoE — top quality, for very high-RAM Macs. Only ~10B experts fire per token, so generation stays usable despite the size.",
    ),

    # ──────────── Qwen3.8 (Aug 2026) ────────────
    ModelEntry(
        repo="mlx-community/Qwen3.8-27B-4bit",
        label="Qwen3.8 27B (4-bit)",
        family="qwen3.8",
        size_gb=16.081,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB. 16.1 GB of weights plus ~2.2 GB at 32K overruns a 24 GB Mac's ~17.2 GB GPU budget.",
        params_b=27,
        quant="4bit",
        is_vision=True,
        best_for="The newest open Qwen — the strongest general-purpose model here that is still Apache-2.0 and locally runnable. Its linear-attention layers keep long documents cheap, which suits research triage and bulk summarization.",
    ),

    # ──────────── Mistral ────────────
    ModelEntry(
        repo="mlx-community/Mistral-7B-Instruct-v0.3-4bit",
        label="Mistral 7B Instruct v0.3 (4-bit)",
        family="mistral",
        size_gb=4.080,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended.",
        params_b=7,
        quant="4bit",
        best_for="A long-standing, permissively-licensed (Apache-2.0) general assistant. Pick this if you want a Llama/Qwen alternative with a different training lineage.",
    ),
    ModelEntry(
        repo="mlx-community/Mistral-Nemo-Instruct-2407-4bit",
        label="Mistral Nemo 12B Instruct (4-bit)",
        family="mistral",
        size_gb=6.905,
        min_unified_memory_gb=16,
        recommended_hardware="M2 Pro / M3 16 GB+ recommended.",
        params_b=12,
        quant="4bit",
        best_for="Mistral and NVIDIA's co-developed 12B model — strong quality, 128K context, Apache-2.0. A solid step up from 7B on 16 GB+ Macs.",
    ),
    ModelEntry(
        repo="mlx-community/Mistral-Small-3.1-24B-Instruct-2503-4bit",
        label="Mistral Small 3.1 24B Instruct (4-bit)",
        family="mistral",
        size_gb=14.119,
        is_vision=True,
        min_unified_memory_gb=24,
        recommended_hardware="24 GB+ unified memory recommended.",
        params_b=24,
        quant="4bit",
        best_for="Mistral's latest 24B — near-frontier quality in a package that fits 24 GB+ Macs. Strong reasoning, good multilingual support, Apache-2.0.",
    ),

    # ──────────── Ministral ────────────
    ModelEntry(
        repo="mlx-community/Ministral-3-3B-Instruct-2512-4bit",
        label="Ministral 3 3B Instruct (4-bit)",
        family="ministral",
        size_gb=2.779,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=3,
        quant="4bit",
        best_for="Mistral's next-gen 3B architecture — noticeably more capable than other 3B-class models. A great everyday pick for any Mac.",
    ),
    ModelEntry(
        repo="mlx-community/Ministral-3-8B-Instruct-2512-4bit",
        label="Ministral 3 8B Instruct (4-bit)",
        family="ministral",
        size_gb=5.631,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended.",
        params_b=8,
        quant="4bit",
        best_for="The larger Ministral — competes with 7B-8B models while being more efficient. Good reasoning, fast generation, Apache-2.0.",
    ),

    # ──────────── Gemma 4 (Apr 2026) ────────────
    # Two builds per size. Verified from each repo's config.json:
    #   plain `-4bit`     → uniform 4-bit, group size 64, no per-layer overrides
    #   `-qat-4bit`       → same 4-bit base, but 123-183 modules pinned to 8-bit
    # Same weights, different quantization recipe — hence the size gap (the 12B
    # is 6.77 GB plain vs 11.02 GB QAT). On the 26B MoE the gap nearly vanishes
    # (15.37 vs 15.64) because the expert tensors stay 4-bit in both, so there
    # the QAT build is essentially free quality.
    ModelEntry(
        repo="mlx-community/gemma-4-E2B-it-4bit",
        label="Gemma 4 E2B Instruct (4-bit)",
        family="gemma4",
        size_gb=3.583,
        is_vision=True,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. ~3.6 GB weights + ~0.25 GB working memory at 32K context.",
        params_b=2,
        quant="4bit",
        best_for="The smallest Gemma 4 and the one to reach for on an 8 GB Mac. Ideal for high-volume mechanical work — titles, tags, descriptions, tagging and classification passes — where you want throughput rather than depth.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-E2B-it-qat-4bit",
        label="Gemma 4 E2B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=4.362,
        is_vision=True,
        min_unified_memory_gb=8,
        recommended_hardware="8 GB fits but with little to spare (~5.4 GB of the ~5.7 GB GPU budget); 16 GB comfortable.",
        params_b=2,
        quant="4bit QAT",
        best_for="The higher-quality E2B build — sensitive layers kept at 8-bit. Worth the extra 0.8 GB over the plain 4-bit if you have 16 GB; on 8 GB take the plain build instead.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-E4B-it-4bit",
        label="Gemma 4 E4B Instruct (4-bit)",
        family="gemma4",
        size_gb=5.179,
        is_vision=True,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB. Too large for an 8 GB Mac's ~5.7 GB GPU budget once working memory is counted.",
        params_b=4,
        quant="4bit",
        best_for="The smaller of the two E4B builds — noticeably stronger than E2B at bulk metadata, summarization, and prompt expansion, and still quick. A good default on a 16 GB machine.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-E4B-it-qat-4bit",
        label="Gemma 4 E4B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=6.831,
        is_vision=True,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB+ recommended for comfortable headroom.",
        params_b=4,
        quant="4bit QAT",
        best_for="The higher-quality E4B build. On a 16 GB Mac this is the best quality-per-GB Gemma 4 that still leaves room for other apps.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-12B-it-4bit",
        label="Gemma 4 12B Instruct (4-bit)",
        family="gemma4",
        size_gb=6.773,
        is_vision=True,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB. Uniform 4-bit, so a dense 12B fits where the 11 GB QAT build cannot.",
        params_b=12,
        quant="4bit",
        best_for="A dense 12B on a 16 GB Mac — the biggest quality jump available at that memory tier. The right pick for bulk work that needs real comprehension: research triage, classification with nuance, rewriting descriptions at volume.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-12B-it-qat-4bit",
        label="Gemma 4 12B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=11.020,
        is_vision=True,
        min_unified_memory_gb=24,
        recommended_hardware="24 GB. Needs ~14.3 GB of the ~17.2 GB GPU budget at 32K context.",
        params_b=12,
        quant="4bit QAT",
        best_for="The best-quality dense 12B. On a 24 GB Mac this is the comfortable everyday choice — full headroom, no context juggling. Step down to the plain 4-bit build for a 16 GB machine.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-26b-a4b-it-4bit",
        label="Gemma 4 26B A4B MoE Instruct (4-bit)",
        family="gemma4",
        size_gb=15.374,
        is_vision=True,
        min_unified_memory_gb=24,
        recommended_hardware="24 GB, and it fills the default GPU budget: ~17.7 GB needed at 32K vs ~17.2 GB available. Keep context at or below 16K, or raise iogpu.wired_limit_mb.",
        params_b=26,
        quant="4bit",
        best_for="The best-shaped model for a 24 GB Mac — 26B of knowledge with only ~4B firing per token, so it answers at closer to 4B speed. Excellent for high-volume metadata and classification where you want quality without waiting.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-26B-A4B-it-qat-4bit",
        label="Gemma 4 26B A4B MoE Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=15.641,
        is_vision=True,
        min_unified_memory_gb=24,
        recommended_hardware="24 GB, same tight fit as the plain build (only 0.27 GB larger). Keep context at or below 16K, or raise iogpu.wired_limit_mb.",
        params_b=26,
        quant="4bit QAT",
        best_for="Same MoE as the plain 4-bit build but with its sensitive layers at 8-bit for almost no extra size — on this model the QAT build is close to free, so prefer it over the plain one.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-31B-it-4bit",
        label="Gemma 4 31B Instruct (4-bit)",
        family="gemma4",
        size_gb=18.444,
        is_vision=True,
        min_unified_memory_gb=36,
        recommended_hardware="36 GB+. Its 16 KV heads make working memory expensive — ~6.2 GB at 32K, the priciest in the Gemma 4 family.",
        params_b=31,
        quant="4bit",
        best_for="The dense 31B in its smaller uniform-4-bit form. Pick this over the QAT build unless you have 64 GB — it is 10 GB lighter for a modest quality cost.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-31B-it-qat-4bit",
        label="Gemma 4 31B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=28.849,
        is_vision=True,
        min_unified_memory_gb=64,
        recommended_hardware="64 GB. 28.8 GB of weights plus ~6.2 GB at 32K exceeds a 48 GB Mac's ~34.4 GB GPU budget.",
        params_b=31,
        quant="4bit QAT",
        best_for="The most capable Gemma 4 — a dense 31B for the hardest reasoning and writing tasks. Reserve for 64 GB Macs.",
    ),

    # ──────────── Gemma 3 (2025, QAT 4-bit) ────────────
    ModelEntry(
        repo="mlx-community/gemma-3-1b-it-qat-4bit",
        label="Gemma 3 1B Instruct (QAT 4-bit)",
        family="gemma3",
        size_gb=0.772,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Tiny and very fast.",
        params_b=1,
        quant="4bit QAT",
        best_for="The lightest model — instant to load, runs anywhere. Good for quick Q&A and testing on memory-constrained Macs.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-3-4b-it-qat-4bit",
        label="Gemma 3 4B Instruct (QAT 4-bit)",
        family="gemma3",
        size_gb=3.035,
        is_vision=True,
        min_unified_memory_gb=8,
        recommended_hardware="8 GB works; 16 GB comfortable. The Gemma 3 sweet spot.",
        params_b=4,
        quant="4bit QAT",
        best_for="The Gemma 3 sweet spot — fast, capable, comfortable on most Macs. A great general-purpose alternative to Llama 3.2 3B with QAT quality.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-3-12b-it-qat-4bit",
        label="Gemma 3 12B Instruct (QAT 4-bit)",
        family="gemma3",
        size_gb=8.068,
        is_vision=True,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB+ unified memory recommended.",
        params_b=12,
        quant="4bit QAT",
        best_for="A strong mid-size assistant — richer reasoning than the 4B while still fitting a 16 GB Mac. The default step-up within Gemma 3.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-3-27b-it-qat-4bit",
        label="Gemma 3 27B Instruct (QAT 4-bit)",
        family="gemma3",
        size_gb=16.873,
        is_vision=True,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB+ recommended.",
        params_b=27,
        quant="4bit QAT",
        best_for="The heavyweight Gemma 3 — top-tier quality. Pick on a 32 GB+ Mac when you want the most from Gemma 3.",
    ),

    ModelEntry(
        repo="mlx-community/Phi-3.5-mini-instruct-4bit",
        label="Phi-3.5 Mini Instruct (4-bit)",
        family="phi",
        size_gb=2.152,
        min_unified_memory_gb=8,
        recommended_hardware="8 GB for short prompts only. This model has no grouped-query attention (32 KV heads), so its working memory grows about four times faster than any other model here — roughly 3.2 GB at 8K context and 12.9 GB at 32K, on top of the weights. Long documents will exhaust an 8 GB Mac.",
        params_b=3.8,
        quant="4bit",
        best_for="Tiny footprint with surprisingly capable reasoning, but strictly a short-prompt model — see the hardware note before feeding it anything long. Phi-4 Mini is the same size, is newer, and handles context four times more cheaply; prefer it unless you specifically want Phi-3.5.",
    ),

    # ──────────── Phi-4 ────────────
    ModelEntry(
        repo="mlx-community/Phi-4-mini-instruct-4bit",
        label="Phi-4 Mini Instruct (4-bit)",
        family="phi4",
        size_gb=2.180,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=3.8,
        quant="4bit",
        best_for="Microsoft's latest compact model — stronger reasoning than Phi-3.5 while staying the same size. Fits any Mac.",
    ),
    ModelEntry(
        repo="mlx-community/Phi-4-mini-reasoning-4bit",
        label="Phi-4 Mini Reasoning (4-bit)",
        family="phi4",
        size_gb=2.180,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=3.8,
        quant="4bit",
        is_reasoning=True,
        best_for="Phi-4 fine-tuned for step-by-step reasoning. Excellent for math, logic, and planning on any Mac — punches well above its weight.",
    ),

    # ──────────── DeepSeek ────────────
    ModelEntry(
        repo="mlx-community/DeepSeek-R1-Distill-Qwen-7B-4bit",
        label="DeepSeek-R1 Distill Qwen 7B (4-bit)",
        family="deepseek",
        size_gb=4.296,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended.",
        params_b=7,
        quant="4bit",
        is_reasoning=True,
        best_for="Reasoning-distilled checkpoint — shows step-by-step thinking. Use for math, logic puzzles, and multi-step planning where you want to verify the reasoning chain.",
    ),
    ModelEntry(
        repo="mlx-community/DeepSeek-R1-Distill-Qwen-14B-4bit",
        label="DeepSeek-R1 Distill Qwen 14B (4-bit)",
        family="deepseek",
        size_gb=8.321,
        min_unified_memory_gb=16,
        recommended_hardware="M2 Pro / M3 16 GB+ recommended.",
        params_b=14,
        quant="4bit",
        is_reasoning=True,
        best_for="The larger reasoning-distilled DeepSeek — significantly better on hard math, science, and logic than the 7B. For 16 GB+ Macs.",
    ),
    ModelEntry(
        repo="mlx-community/DeepSeek-Coder-V2-Lite-Instruct-4bit-mlx",
        label="DeepSeek Coder V2 Lite 16B Instruct (4-bit)",
        family="deepseek",
        size_gb=8.845,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB+ unified memory recommended.",
        params_b=16,
        quant="4bit",
        is_coder=True,
        best_for="DeepSeek's dedicated code model — strong on complex programming tasks, code review, and refactoring. For 16 GB+ Macs. Licence check: the DeepSeek Model Licence permits commercial use but attaches a list of prohibited use cases; read it before shipping.",
    ),

    # ──────────── Devstral ────────────
    ModelEntry(
        repo="mlx-community/Devstral-Small-2-24B-Instruct-2512-4bit",
        label="Devstral Small 2 24B Instruct (4-bit)",
        family="devstral",
        size_gb=15.137,
        min_unified_memory_gb=24,
        recommended_hardware="24 GB+ unified memory recommended.",
        params_b=24,
        quant="4bit",
        best_for="Near-frontier quality at 24B — a great pick for 24 GB+ Macs. Noticeably stronger than smaller models without the massive footprint of a 70B.",
    ),

    # ──────────── LFM ────────────
    ModelEntry(
        repo="mlx-community/LFM2.5-1.2B-Instruct-4bit",
        label="LFM 2.5 1.2B Instruct (4-bit)",
        family="lfm",
        size_gb=0.663,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Tiny and very fast.",
        params_b=1.2,
        quant="4bit",
        best_for="A tiny model from Li Fei-Fei's lab that punches well above its weight. Near-instant load, fast generation — a great alternative to Gemma 3 1B on any Mac.",
    ),

    # ──────────── Nemotron ────────────
    ModelEntry(
        repo="mlx-community/NVIDIA-Nemotron-3-Nano-4B-4bit",
        label="Nemotron 3 Nano 4B (4-bit)",
        family="nemotron",
        size_gb=2.254,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB. Weights are tiny (2.3 GB) but it has no sliding-window attention, so 32K of context costs ~5.6 GB on its own.",
        params_b=4,
        quant="4bit",
        best_for="Built for mechanical bulk work — short, literal answers for extraction, tagging, classification, and metadata at volume. Keep prompts short and it is one of the fastest useful models here; it is not a conversationalist.",
    ),
    ModelEntry(
        repo="mlx-community/NVIDIA-Nemotron-3-Nano-30B-A3B-4bit",
        label="Nemotron 3 Nano 30B-A3B MoE (4-bit)",
        family="nemotron",
        size_gb=17.793,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB. The 17.8 GB of weights alone exceed a 24 GB Mac's ~17.2 GB GPU budget.",
        params_b=30,
        quant="4bit",
        best_for="The bulk-work workhorse of the family — 30B of knowledge, ~3B active per token, and only 2 KV heads so long documents stay cheap. Use it for high-volume triage and summarization on a 32 GB+ Mac.",
    ),
    ModelEntry(
        repo="mlx-community/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-4bit",
        label="Nemotron 3 Nano Omni 30B-A3B Reasoning (4-bit)",
        family="nemotron",
        size_gb=19.651,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB. The largest Nemotron here at 19.7 GB — the weights alone exceed a 24 GB Mac's ~17.2 GB GPU budget. MoE: all 30B in memory, ~3B active per token.",
        params_b=30,
        quant="4bit",
        is_reasoning=True,
        best_for="NVIDIA's reasoning MoE — activates ~3B of 30B params per token and writes out its thinking before answering. Excellent for math, science, and logic; for high-volume mechanical work take the plain 30B-A3B instead, which is smaller and does not spend tokens deliberating.",
    ),
)


def get_model(repo: str) -> Optional[ModelEntry]:
    for m in CATALOG:
        if m.repo == repo:
            return m
    return None


def serialize_model(m: ModelEntry) -> dict:
    try:
        from . import system_info
        fit = system_info.fit_for(m.min_unified_memory_gb)
    except Exception:
        fit = None
    return {
        "repo": m.repo,
        "label": m.label,
        "family": m.family,
        "family_label": FAMILIES[m.family].label,
        "size_gb": m.size_gb,
        "size_gb_approximate": False,
        "gated": m.gated,
        "min_unified_memory_gb": m.min_unified_memory_gb,
        "recommended_hardware": m.recommended_hardware,
        "params_b": m.params_b,
        "quant": m.quant,
        "best_for": m.best_for,
        "is_starter": m.is_starter,
        "is_coder": m.is_coder,
        "is_reasoning": m.is_reasoning,
        "is_vision": m.is_vision,
        "fit": fit,
    }


def serialize_family(f: Family) -> dict:
    return {
        "id": f.id,
        "label": f.label,
        "summary": f.summary,
        "how_to_use": f.how_to_use,
        "context_note": f.context_note,
    }


def companions_for(repo: str) -> tuple[dict, ...]:
    return ()


def ignore_patterns_for(repo: str) -> tuple[str, ...]:
    return ()
