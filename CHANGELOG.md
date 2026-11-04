# Changelog

## Reproducing the published results

The published results (v5, 93 tasks; v6 expansion, 10 tasks; prompt `api/agent/prompts/v3.md`) correspond
to commit `6576859` and are archived on Zenodo: dataset [10.5281/zenodo.20450995](https://doi.org/10.5281/zenodo.20450995),
software [10.5281/zenodo.20450997](https://doi.org/10.5281/zenodo.20450997).

## [Unreleased] — v7

Most `tool_missing` failures in v5/v6 came from the benchmark, not the agents: the v3 prompt pre-loaded
layer metadata and told agents not to call the metadata tools some tasks require, a few tools returned
incomplete results, and some tasks were mis-specified. With the same model before and after (Claude Opus 5.5,
local MCP), `tool_missing` fell from 23 to 0 and passes rose from 51 to 58 of 103. v7 scores are not
comparable with v5/v6.

- **Tools:** `list_layers` includes `bigearthnet_lulc`; `get_legend` returns classes for `bigearthnet_lulc`
  and `mfe` and a description for the INES layers; `get_layer_bounds` works for `bigearthnet_lulc`;
  `reject_task` states each layer's coverage; the MCP server passes the looked-up area to `analyze_area`.
- **Prompt:** new `prompts/v4.md` without pre-loaded data or route rules (`v3.md` unchanged).
- **Tasks:** new `cases/benchmark_v7.json` (v5 + v6, same IDs); 24 tasks corrected: 12 reword "CO2 geological
  storage" as "CO2 absorption" (what the layer measures); the other 12 have a `v7:` note in `ground_truth_notes`.
