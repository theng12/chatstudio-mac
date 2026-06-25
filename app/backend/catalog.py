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
    # Soft note about context length / chat-template behavior for this model
    # family. Omitted (None) rather than guessed when we don't have a
    # verified public number for the specific variant in this catalog.
    context_note: Optional[str] = None


FAMILIES: dict[str, Family] = {
    "llama": Family(
        id="llama",
        label="Llama",
        summary=(
            "Meta's Llama 3.x instruction-tuned chat models, quantized to MLX "
            "by mlx-community. Strong general-purpose assistants with broad "
            "community tooling support."
        ),
        how_to_use=(
            "Load a Llama model in the Chat tab and talk to it like any chat "
            "assistant. The 3B variant is the recommended starter — fast, "
            "small, and good enough for most everyday tasks. Step up to 8B "
            "for noticeably better reasoning and instruction-following."
        ),
        context_note="Llama 3.x models support a 128K context window upstream; actual usable context in this app depends on available unified memory.",
    ),
    "qwen": Family(
        id="qwen",
        label="Qwen",
        summary=(
            "Alibaba's Qwen2.5 instruction-tuned chat models, quantized to MLX "
            "by mlx-community. Strong multilingual support and a dedicated "
            "Coder variant for programming tasks."
        ),
        how_to_use=(
            "Pick the plain Qwen2.5-Instruct variants for general chat, or the "
            "Coder variant specifically for code generation, refactoring, and "
            "debugging help. 14B gives noticeably richer reasoning than 7B if "
            "you have the memory."
        ),
        context_note="Qwen2.5 models support up to a 128K context window upstream (32K native on some sizes); actual usable context here depends on available unified memory.",
    ),
    "mistral": Family(
        id="mistral",
        label="Mistral",
        summary=(
            "Mistral AI's instruction-tuned 7B chat model, quantized to MLX by "
            "mlx-community. Apache-2.0, fast, and a long-standing community "
            "favorite for a lightweight general assistant."
        ),
        how_to_use=(
            "Load it in the Chat tab for general-purpose conversation. A solid "
            "pick when you want a permissively-licensed alternative to Llama "
            "at a similar size."
        ),
        context_note="Mistral-7B-Instruct-v0.3 supports a 32K context window upstream.",
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
    "gemma2": Family(
        id="gemma2",
        label="Gemma 2",
        summary=(
            "Google's previous-generation Gemma 2 instruction-tuned chat "
            "models, quantized to MLX by mlx-community. Still a solid, "
            "lightweight, text-only general assistant — kept for continuity."
        ),
        how_to_use=(
            "Prefer Gemma 3 or Gemma 4 for new work. Reach for Gemma 2 9B if "
            "you specifically want the older generation's behavior, or the 2B "
            "for a tiny, fast text-only assistant."
        ),
        context_note=None,
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
    "deepseek": Family(
        id="deepseek",
        label="DeepSeek",
        summary=(
            "DeepSeek-R1's reasoning-distilled Qwen2.5-7B checkpoint, quantized "
            "to MLX by mlx-community. Trained to show step-by-step reasoning "
            "before answering — useful for math, logic, and multi-step problems."
        ),
        how_to_use=(
            "Use this when a task benefits from explicit step-by-step "
            "reasoning (math word problems, logic puzzles, multi-step "
            "planning). Responses tend to be longer than a plain instruct "
            "model's because the model reasons out loud before concluding."
        ),
        context_note=None,
    ),
}


@dataclass(frozen=True)
class ModelEntry:
    repo: str
    label: str
    family: str
    size_gb: float                       # approximate on-disk size (see module docstring)
    gated: bool = False
    min_unified_memory_gb: int = 8
    recommended_hardware: str = ""
    params_b: float = 0.0                # approximate parameter count, in billions
    quant: str = "4bit"                  # quantization label, e.g. "4bit", "8bit"
    best_for: str = ""
    is_starter: bool = False             # recommended default/starter model
    is_coder: bool = False
    is_reasoning: bool = False


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
        repo="mlx-community/Llama-3.1-8B-Instruct-4bit",
        label="Llama 3.1 8B Instruct (4-bit)",
        family="llama",
        size_gb=4.5,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended for comfortable headroom.",
        params_b=8,
        quant="4bit",
        best_for="Noticeably better reasoning and instruction-following than the 3B model, still comfortably fast on Apple Silicon. The default step-up once you outgrow 3B.",
    ),

    # ──────────── Qwen ────────────
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
        size_gb=8.0,
        min_unified_memory_gb=16,
        recommended_hardware="M2 Pro / M3 16 GB+ recommended for comfortable headroom.",
        params_b=14,
        quant="4bit",
        best_for="The richest general-purpose model in the catalog. Pick this when 7B-class models aren't giving you enough reasoning depth and you have the memory to spare.",
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
        best_for="Dedicated code model — fine-tuned specifically for programming tasks (completion, refactoring, debugging, explaining code). Pick this over the plain Qwen2.5 7B for anything code-related.",
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

    # ──────────── Gemma 4 (Apr 2026, QAT 4-bit) ────────────
    # Sizes below are REAL on-disk totals (sum of HF repo files), not the 4-bit
    # rule-of-thumb estimate, because these QAT + multimodal builds are heavier
    # than a naive 0.6 GB/B guess would suggest.
    ModelEntry(
        repo="mlx-community/gemma-4-E2B-it-qat-4bit",
        label="Gemma 4 E2B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=4.4,
        min_unified_memory_gb=12,
        recommended_hardware="16 GB recommended; runs on less but tight. The 'E2B' MatFormer build is heavier on disk (~4.4 GB) than its effective-2B name implies.",
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
        recommended_hardware="32 GB+ recommended. Mixture-of-Experts: all 26B params live in memory, but only ~4B are active per token, so it generates faster than a dense 26B.",
        params_b=26,
        quant="4bit QAT",
        best_for="Mixture-of-Experts sweet spot — near-large-model quality at closer-to-small-model speed, because only ~4B of the 26B params fire per token. Pick this on a 32 GB+ Mac when you want quality without a dense-31B's slowdown.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-4-31B-it-qat-4bit",
        label="Gemma 4 31B Instruct (QAT 4-bit)",
        family="gemma4",
        size_gb=28.8,
        min_unified_memory_gb=48,
        recommended_hardware="48 GB+ (64 GB comfortable). The most capable model in the catalog; large and slower to load.",
        params_b=31,
        quant="4bit QAT",
        best_for="The most capable Gemma 4 — a dense 31B for the hardest reasoning and writing tasks. Reserve this for high-RAM Macs (48 GB+).",
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
        best_for="The lightest model here — instant to load, runs anywhere. Good for quick Q&A, drafting, and testing the pipeline on memory-constrained Macs.",
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
        best_for="The Gemma 3 sweet spot — fast, capable, and comfortable on most Macs. A great general-purpose alternative to Llama 3.2 3B with QAT quality.",
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
        best_for="The heavyweight Gemma 3 — top-tier quality for the generation. Pick this on a 32 GB+ Mac when you want the most from Gemma 3.",
    ),

    # ──────────── Gemma 2 (previous gen) ────────────
    ModelEntry(
        repo="mlx-community/gemma-2-2b-it-4bit",
        label="Gemma 2 2B Instruct (4-bit)",
        family="gemma2",
        size_gb=1.5,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=2,
        quant="4bit",
        best_for="A tiny, fast previous-gen assistant. Reach for Gemma 3 1B/4B first; keep this if you specifically want Gemma 2 behavior at a small size.",
    ),
    ModelEntry(
        repo="mlx-community/gemma-2-9b-it-4bit",
        label="Gemma 2 9B Instruct (4-bit)",
        family="gemma2",
        size_gb=5.2,
        min_unified_memory_gb=12,
        recommended_hardware="M1 Pro / M2 16 GB recommended.",
        params_b=9,
        quant="4bit",
        best_for="Google's previous-generation mid-size assistant. Gemma 3 4B/12B generally supersede it, but it remains a solid, familiar text-only model.",
    ),

    # ──────────── Phi ────────────
    ModelEntry(
        repo="mlx-community/Phi-3.5-mini-instruct-4bit",
        label="Phi-3.5 Mini Instruct (4-bit)",
        family="phi",
        size_gb=2.2,
        min_unified_memory_gb=8,
        recommended_hardware="Any Apple Silicon Mac with 8 GB.",
        params_b=3.8,
        quant="4bit",
        best_for="Tiny footprint with surprisingly capable reasoning for its size. Pick this on memory-constrained Macs when Llama 3.2 3B isn't quite cutting it on reasoning-heavy prompts.",
    ),

    # ──────────── DeepSeek (reasoning) ────────────
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
        best_for="A reasoning-distilled checkpoint — shows step-by-step thinking before answering. Pick this for math, logic puzzles, and multi-step planning where you want to see (and verify) the reasoning chain, not just the final answer.",
    ),
)


def get_model(repo: str) -> Optional[ModelEntry]:
    for m in CATALOG:
        if m.repo == repo:
            return m
    return None


def serialize_model(m: ModelEntry) -> dict:
    # Per-model hardware-fit verdict against the running Mac's detected RAM.
    # Lazy import dodges any potential cycle at module-load time.
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


# ───────────── Companion (helper) models ─────────────
#
# Kept for structural parity with VoiceStudio's catalog.py shape (which
# downloads.py / main.py expect a `companions_for()` hook to exist). None of
# the chat models in this catalog need a second HF repo at load time — every
# entry is fully self-contained (tokenizer + weights in one mlx-community
# repo) — so this always returns (). If a future model needs a separate
# tokenizer/adapter repo, list it here the same way VoiceStudio's
# FAMILY_COMPANIONS does.
def companions_for(repo: str) -> tuple[dict, ...]:
    return ()


def ignore_patterns_for(repo: str) -> tuple[str, ...]:
    """No per-repo file filtering needed — mlx-community chat repos don't
    ship redundant alternate weight formats the way some TTS repos do."""
    return ()
