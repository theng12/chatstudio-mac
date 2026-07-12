"""
Static catalog of MLX-ready instruction-tuned chat models for Chat Studio (Mac).

Every entry is a pre-quantized, already-MLX-converted repo from the
`mlx-community` Hugging Face org — no conversion step needed, `mlx_lm.load`
can load these directly. Each entry describes the HF repo plus metadata the UI
uses: approximate download size, hardware floor, family grouping, and a
"best for" note.

Sizing note: exact on-disk sizes are NOT verified against the live HF API at
catalog-definition time (that would require a network call per entry). The
`size_gb` values below are APPROXIMATE, using the well-known public rule of
thumb for 4-bit quantization: ~0.5-0.7 GB per billion parameters (similar
ballpark for 8-bit families, listed per-entry). They are good enough for the
UI's download-size hint and hardware-fit calculation, but the live `/api/cache`
+ `/api/downloads` endpoints report the REAL bytes once a model is on disk —
treat `size_gb` here as an estimate, not a guarantee.

MoE (Mixture-of-Experts) models load ALL experts into memory — the total
param count determines the RAM floor even though only a subset activates per
token. Their size_gb is estimated the same way as dense models.
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
        context_note="Llama models support long context windows (128K for 3.x, up to 1M for 4 Scout); actual usable context depends on available unified memory.",
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
            "models to date, natively multimodal and Apache-2.0 licensed. "
            "Includes ultra-efficient MatFormer 'E' variants (E2B / E4B), a 26B "
            "Mixture-of-Experts that activates only ~4B params per token, and a "
            "dense 31B. All entries here are the QAT (quantization-aware "
            "trained) 4-bit builds, which keep close to full-precision quality."
        ),
        how_to_use=(
            "Start with E2B or E4B — the MatFormer 'effective' variants give "
            "strong quality for their speed. Step up to 12B or the 26B MoE for "
            "deeper reasoning if you have the memory, or the dense 31B on a "
            "high-RAM Mac. Pick a size whose fit chip is green for your machine."
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
            "from Devstral AI, quantized to MLX by mlx-community. Strong "
            "general-purpose quality competitive with much larger models."
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
            "LFM 2.5 (Li Fei-Fei Lab, Stanford) — a tiny 1.2B instruction-"
            "tuned model that punches well above its weight class, quantized "
            "to MLX by mlx-community."
        ),
        how_to_use=(
            "An excellent tiny model for 8 GB Macs. Nearly instant to load, "
            "fast generation, and surprisingly capable reasoning for its "
            "size. A great alternative to Gemma 3 1B and Llama 3.2 1B."
        ),
        context_note=None,
    ),
    "nemotron": Family(
        id="nemotron",
        label="Nemotron",
        summary=(
            "NVIDIA's Nemotron 3 Nano Omni (2025) — a 30B MoE reasoning "
            "model that activates only ~3B params per token. Designed for "
            "efficient step-by-step reasoning on math, science, and logic "
            "tasks. Quantized to MLX by mlx-community."
        ),
        how_to_use=(
            "Use this for tasks that benefit from explicit reasoning: "
            "math, science, coding puzzles, multi-step planning. The MoE "
            "architecture keeps generation fast despite the 30B knowledge "
            "footprint."
        ),
        context_note="Nemotron 3 Nano Omni activates ~3B of its 30B params per token; all 30B are loaded in memory. Supports a 128K context window upstream.",
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
        size_gb=1.8,
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
        size_gb=0.7,
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
        size_gb=4.5,
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
        size_gb=61.1,
        min_unified_memory_gb=64,
        recommended_hardware="16 GB+ recommended. MoE: all 17B params in memory, ~4B active per token for fast generation.",
        params_b=17,
        quant="4bit",
        best_for="Meta's latest MoE model — strong quality at a reasonable footprint. Generates faster than a dense 17B would because only ~4B experts fire per token.",
    ),
    ModelEntry(
        repo="mlx-community/Llama-3.3-70B-Instruct-4bit",
        label="Llama 3.3 70B Instruct (4-bit)",
        family="llama",
        size_gb=39.7,
        min_unified_memory_gb=48,
        recommended_hardware="48 GB+ (64 GB+ comfortable). The largest Llama in the catalog.",
        params_b=70,
        quant="4bit",
        best_for="The most capable Llama — top-tier reasoning, writing, and instruction-following. Reserve for high-RAM Macs (48 GB+).",
    ),

    # ──────────── Qwen ────────────
    ModelEntry(
        repo="mlx-community/Qwen2.5-0.5B-Instruct-4bit",
        label="Qwen2.5 0.5B Instruct (4-bit)",
        family="qwen",
        size_gb=0.3,
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
        size_gb=0.9,
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
        size_gb=1.7,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Fast load and generation.",
        params_b=3,
        quant="4bit",
        best_for="The sweet spot tiny Qwen — more capable than 1.5B while fitting any Mac. A strong Llama 3.2 3B alternative with Qwen's multilingual strengths.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen2.5-7B-Instruct-4bit",
        label="Qwen2.5 7B Instruct (4-bit)",
        family="qwen",
        size_gb=4.3,
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
        size_gb=8.3,
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
        size_gb=18.4,
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
        size_gb=0.9,
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
        size_gb=4.3,
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
        size_gb=8.3,
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
        size_gb=2.3,
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
        size_gb=17.2,
        min_unified_memory_gb=24,
        recommended_hardware="16 GB+ recommended. MoE: all 30B in memory, ~3B active per token.",
        params_b=30,
        quant="4bit",
        is_coder=True,
        best_for="A fast MoE code model — activates only ~3B params per token for quick generation while keeping 30B of knowledge loaded. Top-tier code quality on 16 GB+ Macs.",
    ),

    # ──────────── Qwen3.5 (Vision-Language) ────────────
    # Unified VL models — load via mlx-vlm (is_vision=True), accept image input.
    # -MLX-4bit naming for the small dense sizes, plain -4bit for the larger MoE.
    ModelEntry(
        repo="mlx-community/Qwen3.5-4B-MLX-4bit",
        label="Qwen3.5 4B (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=3.1,
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
        size_gb=6.0,
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
        size_gb=0.7,
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
        size_gb=1.7,
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
        size_gb=16.1,
        min_unified_memory_gb=24,
        recommended_hardware="M-series with 24 GB+ unified memory.",
        params_b=27,
        quant="4bit",
        is_vision=True,
        best_for="The dense 27B — noticeably stronger image + text reasoning than the 9B. For 24 GB+ Macs that want top vision quality.",
    ),
    ModelEntry(
        repo="mlx-community/Qwen3.5-35B-A3B-4bit",
        label="Qwen3.5 35B-A3B MoE (Vision, MLX 4-bit)",
        family="qwen3.5",
        size_gb=20.4,
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
        size_gb=69.6,
        min_unified_memory_gb=96,
        recommended_hardware="96 GB+ unified memory (Mac Studio / high-RAM MacBook Pro). ~10B params active per token.",
        params_b=122,
        quant="4bit",
        is_vision=True,
        best_for="The flagship Qwen3.5 vision MoE — top quality, for very high-RAM Macs. Only ~10B experts fire per token, so generation stays usable despite the size.",
    ),

    # ──────────── Mistral ────────────
    ModelEntry(
        repo="mlx-community/Mistral-7B-Instruct-v0.3-4bit",
        label="Mistral 7B Instruct v0.3 (4-bit)",
        family="mistral",
        size_gb=4.1,
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
        size_gb=6.9,
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
        size_gb=14.1,
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
        size_gb=2.8,
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
        size_gb=5.6,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended.",
        params_b=8,
        quant="4bit",
        best_for="The larger Ministral — competes with 7B-8B models while being more efficient. Good reasoning, fast generation, Apache-2.0.",
    ),

    # ──────────── Gemma 4 (Apr 2026, QAT 4-bit) ────────────
    ModelEntry(
        repo="mlx-community/gemma-4-E2B-it-qat-4bit",
        label="Gemma 4 E2B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=4.4,
        min_unified_memory_gb=12,
        recommended_hardware="16 GB recommended; runs on less but tight.",
        params_b=2,
        quant="4bit QAT",
        best_for="The smallest, fastest Gemma 4. A MatFormer 'effective-2B' build that punches above its weight — a great default Gemma 4 to try first on most Macs.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-E4B-it-qat-4bit",
        label="Gemma 4 E4B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=6.8,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB+ recommended for comfortable headroom.",
        params_b=4,
        quant="4bit QAT",
        best_for="The larger MatFormer 'effective-4B' build — noticeably stronger than E2B while staying friendly to 16 GB Macs. A solid everyday Gemma 4 pick.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-12B-it-qat-4bit",
        label="Gemma 4 12B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=11.0,
        min_unified_memory_gb=24,
        recommended_hardware="24 GB+ unified memory recommended.",
        params_b=12,
        quant="4bit QAT",
        best_for="A dense 12B with strong reasoning. Step up here from the E-variants when you want more depth and have 24 GB+ to work with.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-26B-A4B-it-qat-4bit",
        label="Gemma 4 26B A4B MoE Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=15.6,
        min_unified_memory_gb=32,
        recommended_hardware="32 GB+ recommended. MoE: all 26B in memory, ~4B active per token.",
        params_b=26,
        quant="4bit QAT",
        best_for="MoE sweet spot — near-large-model quality at closer-to-small-model speed. Pick this on a 32 GB+ Mac for quality without the 31B's slowdown.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-31B-it-qat-4bit",
        label="Gemma 4 31B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=28.8,
        min_unified_memory_gb=48,
        recommended_hardware="48 GB+ (64 GB comfortable). The most capable model in the catalog.",
        params_b=31,
        quant="4bit QAT",
        best_for="The most capable Gemma 4 — a dense 31B for the hardest reasoning and writing tasks. Reserve for high-RAM Macs (48 GB+).",
    ),

    # ──────────── Gemma 3 (2025, QAT 4-bit) ────────────
    ModelEntry(
        repo="mlx-community/gemma-3-1b-it-qat-4bit",
        label="Gemma 3 1B Instruct (QAT 4-bit)",
        family="gemma3",
        size_gb=0.8,
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
        size_gb=3.0,
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
        size_gb=8.1,
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
        size_gb=16.9,
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
        size_gb=2.2,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=3.8,
        quant="4bit",
        best_for="Tiny footprint with surprisingly capable reasoning. Pick on memory-constrained Macs when Llama 3.2 3B isn't quite cutting it on reasoning-heavy prompts.",
    ),

    # ──────────── Phi-4 ────────────
    ModelEntry(
        repo="mlx-community/Phi-4-mini-instruct-4bit",
        label="Phi-4 Mini Instruct (4-bit)",
        family="phi4",
        size_gb=2.2,
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
        size_gb=2.2,
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
        size_gb=4.3,
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
        size_gb=8.3,
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
        size_gb=8.8,
        min_unified_memory_gb=16,
        recommended_hardware="16 GB+ unified memory recommended.",
        params_b=16,
        quant="4bit",
        is_coder=True,
        best_for="DeepSeek's dedicated code model — strong on complex programming tasks, code review, and refactoring. For 16 GB+ Macs.",
    ),

    # ──────────── Devstral ────────────
    ModelEntry(
        repo="mlx-community/Devstral-Small-2-24B-Instruct-2512-4bit",
        label="Devstral Small 2 24B Instruct (4-bit)",
        family="devstral",
        size_gb=15.1,
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
        size_gb=0.7,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB. Tiny and very fast.",
        params_b=1.2,
        quant="4bit",
        best_for="A tiny model from Li Fei-Fei's lab that punches well above its weight. Near-instant load, fast generation — a great alternative to Gemma 3 1B on any Mac.",
    ),

    # ──────────── Nemotron (reasoning) ────────────
    ModelEntry(
        repo="mlx-community/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-4bit",
        label="Nemotron 3 Nano Omni 30B-A3B Reasoning (4-bit)",
        family="nemotron",
        size_gb=19.7,
        min_unified_memory_gb=24,
        recommended_hardware="16 GB+ recommended. MoE: all 30B in memory, ~3B active per token.",
        params_b=30,
        quant="4bit",
        is_reasoning=True,
        best_for="NVIDIA's efficient reasoning MoE — activates ~3B of 30B params per token for fast step-by-step thinking. Excellent for math, science, and logic on 16 GB+ Macs.",
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
        "size_gb_approximate": True,
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
