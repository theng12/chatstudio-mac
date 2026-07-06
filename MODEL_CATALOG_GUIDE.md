# Chat Studio Model Catalog Guide

This guide is the source of truth for keeping the family-first Models tab organized. The catalog has three distinct layers. Do not mix them:

1. **Local family**: a model lineage such as Llama, Qwen, or Gemma. Families explain shared behavior and are the primary navigation in the Local MLX tab.
2. **Local variant**: one downloadable MLX repository within a family. Variants compare parameter count, quantization, download size, minimum unified memory, and specialty.
3. **Cloud provider**: a hosted API such as OpenRouter or NVIDIA NIM. Providers are the primary navigation in the Cloud tab; their hosted models are options beneath them.

Hugging Face discovery is intentionally separate. It finds MLX repositories beyond the curated catalog, but search results do not become curated families automatically.

## Files That Own The Catalog

- `app/backend/catalog.py`: local families and curated MLX variants.
- `app/backend/providers.py`: cloud providers and their curated hosted models.
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
- `min_unified_memory_gb` is the practical loading floor, not the model file size.
- `params_b` is total parameters loaded into memory. For MoE models, use total parameters, not active parameters.
- `quant` uses compact values such as `4bit`, `8bit`, or `bf16`.
- `best_for` explains the decision in user language.
- Set specialty flags only when the model is deliberately positioned for that role. A variant can be `is_coder` or `is_reasoning`; `is_starter` should be rare.

Keep variants from the same lineage together in `CATALOG`. The UI preserves catalog order by default and creates family panels automatically.

## Cloud Taxonomy

Cloud providers live in `PROVIDERS` in `app/backend/providers.py`. Add hosted options to the provider's `models` tuple:

```python
CloudModel(
    id="publisher/example-model",
    label="Example Model",
    notes="Fast generalist · long context",
    free=True,
),
```

Use the provider's exact API model ID. Keep `notes` short because it is the comparison text in the variant row. Set `free=False` for billed models; those remain hidden until the user explicitly enables paid models in Settings. Do not create local `ModelEntry` records for cloud-only models.

For providers with a changing catalog, retain the existing live-listing mechanism instead of copying hundreds of models into the curated tuple. Live results are merged and deduplicated by repository ID in the UI.

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
python -m py_compile app/backend/catalog.py app/backend/providers.py app/backend/hub.py app/backend/main.py
node --check app/frontend/app.js
git diff --check
```

With the service running on port `47871`:

```bash
curl -fsS http://127.0.0.1:47871/api/catalog | python -m json.tool >/dev/null
curl -fsS http://127.0.0.1:47871/api/providers | python -m json.tool >/dev/null
```

In the Models tab, verify:

- The new local family appears once and expands to all of its variants.
- Search finds both the family name and repository ID.
- Parameter, quantization, size, and RAM values are correct.
- RAM filters do not hide models on a fresh page load.
- Download, cancel, Chat, and Set as default still work.
- The Cloud tab groups models under the correct provider and respects key/paid state.
- Hub search can find, download, and later load a non-curated MLX chat model.
- The layout remains readable around 1280 px, 900 px, and 390 px widths.

Never edit Pinokio launcher scripts for a catalog-only update. The model library is driven entirely by backend catalog data and existing app APIs.
