# GeoAgentBench — Benchmark Cases

This directory contains all benchmark case definitions used to evaluate GeoNatureAgent. Each JSON file is a named case set registered in `case_loader.py`.

---

## Case Sets

| Set name | File | Cases | Status | Purpose |
|----------|------|-------|--------|---------|
| `dev` | `dev.json` | 6 | Reference | Quick smoke test during development |
| `v1` | `benchmark_v1.json` | 20 | Archive | Original benchmark |
| `v2` | `benchmark_v2.json` | 8 | Archive | Extended v1 |
| `v3` | `benchmark_v3.json` | 30 | Archive | Province/municipality benchmark |
| `v4` | `benchmark_v4.json` | 10 | Archive | Habitat cover (Phase 2) |
| `poc` | `poc_murcia_cordoba_jaen.json` | 4 | Archive | PoC 3-province study |
| `poc_v2` | `benchmark_poc_v2.json` | 9 | Archive | Extended PoC |
| **`v5`** | **`benchmark_v5.json`** | **93** | **FINAL** | **Unified paper benchmark** |

**v5 is the final benchmark for the paper.** All metrics, figures, and tables in the publication are produced from v5. No further case additions after DAAS-48 closes.

---

## benchmark_v5.json — Category Overview

v5 merges all prior versions (v3 + v4) and adds cases to cover categories that scored 0% in early runs. It is the final, canonical benchmark used in the paper.

| Category | Cases | IDs | Description |
|----------|-------|-----|-------------|
| `comparison` | 2 | V5_21--22 | Province pair comparison with `compare_areas` |
| `cross_indicator` | 8 | V5_13--14, V5_38, V5_67--69, V5_86--87 | Multi-indicator reasoning (CO2 + erosion + BigEarthNet land cover) |
| `deep_dive` | 6 | V5_23, V5_73, V5_87, V5_91--93 | Full multi-indicator profile + chart |
| `error_handling` | 6 | V5_15--18, V5_39--40 | Hallucination prevention, unavailable data |
| `error_recovery` | 3 | V5_46--48 | Graceful fallback when data is unavailable |
| `habitat_analysis` | 7 | V5_31--35, V5_56 | BigEarthNet V2 land cover (Portugal districts, session recall) |
| `interpretation` | 7 | V5_24, V5_70--72, V5_88--90 | Policy reasoning from data |
| `language` | 6 | V5_27--28, V5_53--54, V5_94--95 | Galician, Basque inputs |
| `memory` | 6 | V5_05--08, V5_36--37 | Multi-turn recall from `session_history` |
| `multi_municipality_ranking` | 3 | V5_41--43 | Rank municipalities within a province |
| `municipality` | 4 | V5_01--04 | Municipality-level analysis with `lookup_municipality` |
| `province_aggregation` | 2 | V5_44--45 | Aggregate stats across a CCAA |
| `ranking` | 2 | V5_19--20 | Top-N queries with `find_top_n` |
| `single_analysis` | 2 | V5_29--30 | Basic single-province single-indicator queries |
| `spatial_reasoning` | 4 | V5_09--12 | Geographic knowledge (regions, islands, CCAA) |
| `temporal_change` | 1 | V5_57 | Cross-country temporal context (BigEarthNet 2018 baseline) |
| `threshold` | 3 | V5_49--51 | Filter by numeric threshold |
| `tool_selection` | 21 | V5_25--26, V5_58--66, V5_74, V5_76--78, V5_80--84, V5_99 | Chart type, legend, list layers, multi-layer toggle |

**Total: 93 cases** — 18 categories, 3 difficulty levels

---

## Available Indicators

| Indicator ID | Type | Years | Coverage | Description |
|-------------|------|-------|----------|-------------|
| `co2_spain_legislation` | Categorical | 2026 | Spain | CO2 absorption project suitability (Not eligible / Conditional / Eligible) per MITECO criteria |
| `rf_gully_probability` | Continuous | 2022 | Europe + UK | Gully erosion probability 0–100% (Random Forest, LUCAS 2022) |
| `bigearthnet_lulc` | Categorical | 2018 | Portugal (9 districts) | 7-class land cover from BigEarthNet V2 (Clasen et al. 2024) — 75k+ labeled Sentinel-2 patches |

Display-only layers (toggle via `toggle_layer` but no `analyze_area`): `ines_erosion_potencial`, `ines_movimientos_masa`, `ines_erosion_eolica`, `burnt_areas`, `mfe`, `lucas_gully_channels`, `lucas_gully_locations`.

---

## Case JSON Schema

All fields accepted by the scoring engine:

```json
{
  "id": "V5_01_...",
  "category": "municipality",
  "difficulty": "easy | medium | hard",
  "description": "One-line summary of what this tests",
  "question": "The user prompt sent verbatim to the agent",

  "expected_tools": ["lookup_municipality", "analyze_area"],
  "expected_actions": ["fly_to_bounds"],

  "must_contain": ["keyword1", "%"],
  "must_not_contain": ["error", "not found"],

  "max_rounds": 4,
  "max_cost_usd": 0.10,
  "max_latency_ms": 30000,

  "ground_truth": [
    {"label": "Navarra", "expected_pct": 64.6, "tolerance": 3.0}
  ],
  "ground_truth_notes": "Human explanation of expected behavior and live data values",

  "session_history": [...]
}
```

**Scoring checks** (see `geoagentbench/scoring.py`):

| Field | Check function | Metric |
|-------|---------------|--------|
| `expected_tools` | `check_expected_tools` | Tool F1 (H) |
| `expected_actions` | `check_expected_actions` | Action F1 (H2) |
| `must_contain` | `check_must_contain` | Keyword coverage (G) |
| `must_not_contain` | `check_must_not_contain` | Keyword coverage (G) |
| `ground_truth` | `check_numeric_accuracy` | Numeric accuracy (A) |
| `expected_tools` + `generate_chart` | `check_chart_generated` | Chart check (B) |
| `max_rounds` | `check_max_rounds` | Efficiency (D) |
| `max_cost_usd` | `check_cost_budget` | Efficiency (D) |
| `max_latency_ms` | `check_latency_budget` | Latency (I) |

**Difficulty weighting** (`geoagentbench/metrics.py:difficulty_weighted_accuracy`): easy=1, medium=2, hard=3.

---

## Adding New Cases

### Interactive mode
```bash
python scripts/add_benchmark_case.py --target v5
```

### Import from JSON
```bash
python scripts/add_benchmark_case.py --import my_case.json --target v5
```

### Validate
```bash
# Validate a single file
python scripts/add_benchmark_case.py --validate geoagentbench/cases/benchmark_v5.json

# Validate all files
python scripts/add_benchmark_case.py --validate-all
```

### Valid categories
`single_analysis`, `comparison`, `ranking`, `interpretation`, `memory`, `language_understanding`, `tool_selection`, `error_handling`, `spatial_reasoning`, `cross_indicator`, `municipality`, `deep_dive`, `poc`, `habitat_analysis`, `temporal_change`, `multi_municipality_ranking`, `province_aggregation`, `error_recovery`, `threshold`, `language`

### Valid tools
`list_layers`, `get_legend`, `analyze_area`, `get_layer_bounds`, `lookup_province`, `lookup_municipality`, `compare_areas`, `find_top_n`, `generate_chart`, `analyze_multi_layer`, `toggle_layer`

---

## v5 Design Decisions

### Why v5 is a unified merge (not additive)
run_001 showed 0% pass rate on `comparison`, `cross_indicator`, `language_understanding`, and chart tasks across all 7 models. The root causes were case design issues, not model failures alone:
- `comparison` cases expected `lookup_province + analyze_area` but `compare_areas` is the correct single-call path → fixed in v5
- `tool_selection` chart case (V3_25) had insufficient round/cost budget → increased in v5

Having a single canonical file avoids `case_set: all` aggregation ambiguity in paper results.

### session_history design
Cases with `session_history` inject a pre-populated conversation before the test question. This tests memory recall and multi-turn coherence without requiring live prior turns. Tool results in the history use synthetic but plausible values consistent with real raster data.

### ground_truth for live rasters
Cases that call live raster analysis (`analyze_area`) cannot have exact ground truth because values depend on AOI geometry at query time. These use `"ground_truth": []` with a detailed `ground_truth_notes` explaining expected behavior. Cases with `session_history` injecting synthetic tool results CAN have `ground_truth` because the values are fixed in the history.