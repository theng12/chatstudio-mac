# Chat Studio Model Catalog Guide

This guide is the source of truth for keeping the local, family-first Models tab organized. The catalog has two distinct layers. Do not mix them:

1. **Local family**: a model lineage such as Llama, Qwen, or Gemma. Families explain shared behavior and are the primary navigation in the Models tab.
2. **Local variant**: one downloadable MLX repository within a family. Variants compare parameter count, quantization, download size, minimum unified memory, and specialty.

Hugging Face discovery is intentionally separate. It finds MLX repositories beyond the curated catalog, but search results do not become curated families automatically.

## Files That Own The Catalog

- `app/backend/catalog.py`: local families and curated MLX variants.
- `app/backend/hub.py`: Hugging Face MLX search and non-chat filtering.
- `app/frontend/index.html`: family-first presentation only. Do not hardcode model entries here.
- `app/frontend/app.js`: filtering, grouping, RAM fit, Hub search, and model actions.

## Local Taxonomy

A local model belongs to exactly one `Family`. Use an architecture or named model lineage as the family, not the publisher and not `mlx-community`. Examples: `qwen3`, `gemma4`, `llama`.

Add a new family to `FAMILIES` in `app/backend/catalog.py`:

```python
"example": Family(
    id="example",
    label="Example",
    summary="One concise description of the lineage and its strengths.",
    how_to_use="Plain-language advice about which variant to choose.",
    context_note="Optional context-window or modality limitation.",
),
```

Then add each downloadable option to `CATALOG`:

```python
ModelEntry(
    repo="mlx-community/Example-7B-Instruct-4bit",
    label="Example 7B Instruct (4-bit)",
    family="example",
    size_gb=4.2,
    min_unified_memory_gb=12,
    recommended_hardware="16 GB recommended for comfortable headroom.",
    params_b=7,
    quant="4bit",
    best_for="A concrete description of the tasks this variant handles well.",
    is_starter=False,
    is_coder=False,
    is_reasoning=False,
),
```

Field rules:

- `repo` must be the exact Hugging Face repository accepted by `mlx_lm.load`.
- `label` names the generation, parameter size, tuning, and quantization. Do not repeat promotional prose.
- `family` must match an existing `FAMILIES` key.
- `size_gb` is decimal GB and is approximate until downloaded.
- `min_unified_memory_gb` is the practical loading floor, not the model file size. See "Deriving the memory floor" below.
- `params_b` is total parameters loaded into memory. For MoE models, use total parameters, not active parameters.
- `quant` uses compact values such as `4bit`, `8bit`, or `bf16`.
- `best_for` explains the decision in user language.
- Set specialty flags only when the model is deliberately positioned for that role. A variant can be `is_coder` or `is_reasoning`; `is_starter` should be rare.

Keep variants from the same lineage together in `CATALOG`. The UI preserves catalog order by default and creates family panels automatically.

## Deriving The Memory Floor

`min_unified_memory_gb` names a machine RAM tier, but the number that actually
decides whether a load succeeds is the GPU working set. macOS gives Metal about
66.67% of unified memory by default (`iogpu.wired_limit_mb = 0`) — a 16 GB M4
Mac mini reports a maximum recommended working set of 10922 MB, exactly two
thirds of 16 GiB. Sizing against total RAM makes every floor optimistic by a
third.

Use:

```
weights (size_gb) + KV cache at 32K context + 0.8 GB runtime overhead
    <= 0.6667 * tier
```

Usable budget in decimal GB is roughly `tier * 0.716`:

| tier | 8 | 16 | 24 | 32 | 36 | 48 | 64 | 96 | 128 |
|---|---|---|---|---|---|---|---|---|---|
| budget GB | 5.7 | 11.4 | 17.2 | 22.9 | 25.8 | 34.4 | 45.8 | 68.7 | 91.6 |

Compute the KV term from the repository's own `config.json` rather than from
parameter count — it varies by an order of magnitude between architectures of
the same size. Read `num_hidden_layers`, `num_key_value_heads`, `head_dim`, and
the attention layout, then take 2 bytes per element for fp16 (this app sets no
`kv_bits` and no `max_kv_size`, so the cache is unquantized and unbounded):

- `layer_types` present — count `full_attention` layers at the full 32K,
  `sliding_attention` layers at `min(sliding_window, 32K)`, and treat
  `linear_attention` layers as a small constant. This is Gemma 4 and Qwen3.5+.
- `sliding_window_pattern: N` — one global layer every N. This is Gemma 3.
- `use_sliding_window: false` — ignore `sliding_window`, it is full attention.
  This is Qwen2.5 and the DeepSeek R1 distills.
- Otherwise full attention on every layer.

Worked examples: Gemma 4 26B A4B costs 1.6 GB at 32K, while Phi-3.5-mini — same
era, a fifth the parameters, but 32 KV heads and no grouped-query attention —
costs 12.9 GB.

`test_catalog.py` enforces two invariants: an entry's weights must fit inside
the GPU budget of its declared floor, and no entry may claim a lower floor than
a smaller sibling in the same family.

## Licences Have No Field

`ModelEntry` has no licence field, and this guide does not add one. Several
catalogued models carry terms that matter to anyone selling a product — a
non-commercial research licence, a monthly-active-user cap, a revenue cap, a
mandatory attribution string. Until a field exists, state the constraint in
plain language in `best_for` for a single entry, or in the family's
`context_note` when it applies to the whole lineage. Do not leave a restricted
licence unlabelled.

## Hugging Face Discovery

The advanced discovery panel calls `GET /api/hub/search`, which is already filtered to the Hugging Face `mlx` tag and removes clearly non-chat pipelines. Downloading a result uses the same queue as curated models. A discovered model remains outside the curated family library until it receives deliberate family metadata in `catalog.py`.

Before promoting a discovered repository into the catalog, confirm:

- It loads with the installed `mlx_lm` version.
- It is instruction/chat tuned rather than a base, embedding, audio, or image model.
- Its repository size and quantization are correctly described.
- Its family, parameter count, and practical RAM floor are known.
- Its chat template works through Chat Studio's existing load and generation flow.

## Verification Checklist

Run from the repository root:

```bash
python -m py_compile app/backend/catalog.py app/backend/hub.py app/backend/main.py
node --check app/frontend/app.js
git diff --check
```

With the service running on port `47871`:

```bash
curl -fsS http://127.0.0.1:47871/api/catalog | python -m json.tool >/dev/null
```

In the Models tab, verify:

- The new local family appears once and expands to all of its variants.
- Search finds both the family name and repository ID.
- Parameter, quantization, size, and RAM values are correct.
- RAM filters do not hide models on a fresh page load.
- Download, cancel, Chat, and Set as default still work.
- Hub search can find, download, and later load a non-curated MLX chat model.
- The layout remains readable around 1280 px, 900 px, and 390 px widths.

Never edit Pinokio launcher scripts for a catalog-only update. The model library is driven entirely by backend catalog data and existing app APIs.
