# Data Catalog — GeoNatureAgent

This directory documents the data available to the agent. Any agent or model
(Claude, Gemini, GPT-4, etc.) can use `layers_registry.yaml` to understand what
data exists, how to interpret it, and how to call the right tools.

## Files

| File | Purpose |
|------|---------|
| `layers_registry.yaml` | Structured catalog of all layers: type, resolution, interpretation, agent notes |

## How the Agent Uses This Data

The agent does not read this YAML directly at runtime. Instead:

1. **Raster layers** are accessed via the `analyze_area` or `analyze_multi_layer` tools,
   which call `darwin_geo_core.cache_manager.get_tile_url(indicator, year, season)`
   to resolve the GCS path at runtime.

2. **Pre-computed data** (`province_rankings.json`) is accessed via the `find_top_n`
   tool — no raster reads required, instant response.

3. **Display-only layers** are toggled via `toggle_layer` — no statistics available.

The system prompt (`api/agent/prompts/v3.md`) embeds the key interpretation context
from this catalog so the agent can reason correctly without tool calls for basic
domain questions.

## Adding a New Layer

1. Add an entry to `layers_registry.yaml` under the appropriate section.
2. Register the layer in `api/active-layers.json` (required for `cache_manager` to
   resolve its GCS path).
3. If it needs a color/legend: add to `api/symbology/symbologies.json`.
4. Update the system prompt if the layer needs domain-specific interpretation guidance.

## AOI for Current PoC

The initial Area of Interest is **Murcia, Córdoba, and Jaén** (southeastern Spain).
Both raster layers (`co2_spain_legislation`, `rf_gully_probability`) cover the full
Spanish mainland, so all three provinces are fully supported.
