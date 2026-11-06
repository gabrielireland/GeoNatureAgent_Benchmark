# Ablation: benchmark-induced `tool_missing` failures (v7)

Post-publication ablation of the GeoNatureAgent Benchmark paper (Diaz Ireland et al., ACM SIGSPATIAL 2026;
software DOI [10.5281/zenodo.20450997](https://doi.org/10.5281/zenodo.20450997), dataset DOI
[10.5281/zenodo.20450995](https://doi.org/10.5281/zenodo.20450995)). It does **not** change the published
results, which stay reproducible from commit `6576859`. Not peer reviewed.

## Question

The paper reports that 68% of failed runs are `tool_missing` (the expected tool was never called) and reads this
as a failure of spatial-operation choice. How much of that comes from the agents, and how much from the benchmark
itself?

## 1. Audit of the published runs (`audit/`)

All 972 `tool_missing` runs of the published results, classified from the raw traces (blind second labeller: 91%
agreement on the family). Four causes:

| Cause | Share of `tool_missing` |
|---|---:|
| Answer already in the system prompt: the v3 prompt pre-loaded layer metadata and told agents not to call the metadata tools that 17 of 21 tool-selection tasks require | 33% |
| Harness or format: the call was written as text and never executed | 20% |
| The agent chose not to act (rejected, asked, answered from knowledge) | 21% |
| The chain broke or took another route | 26% |

Read: a large share of `tool_missing` is benchmark-induced (prompt, tools, task wording), so the paper's
tool-selection figures understate what the agents can do. The first cause can also be read as an intended test
(do agents verify instead of trusting context); both readings are kept. Details: `audit/REPORT.md`.

## 2. Before/after test of the fix (`before_after/`)

The v7 fix (commit `acdeb61`, see `CHANGELOG.md`) changes tools, the prompt (`prompts/v4.md`) and 24 tasks.
Decision criteria were written down before the run: `before_after/LOCK_before_after.md`.

| | Before (v3 prompt, published code) | After (v7) |
|---|---:|---:|
| `tool_missing` failures | 23 | 3 (0 with 3 task changes made after seeing the results) |
| Tasks passed (of 103) | 51 | 57 (58 with those 3 changes) |

Verdict by the locked rule: **PARTLY**. The fixed causes account for the drop in `tool_missing`, but under the
v3 prompt this model still called the metadata tool in 59% of metadata tasks, so the prompt suppressed metadata
calls less for this model than for the published ones (8 to 33%).

**Limits:** one model (Claude Opus 5.5 as a Claude Code agent over the local MCP server), one run each, and the
same model family as the author of the fixes. v7 scores are not comparable with the v5/v6 leaderboard. A
multi-model, multi-seed run is the next step.

## Files

| Path | What |
|---|---|
| `audit/REPORT.md` | The audit, with figures in `audit/figures/` |
| `audit/tables/`, `audit/data/` | Per-run classifications, summaries, blind-labeller agreement, robustness checks, rescored leaderboard |
| `audit/scripts/01..12_*.py` | Pipeline; `01` needs the raw agent traces (`GNA_RAW_TRACES`), the rest run from `audit/data/` |
| `before_after/LOCK_before_after.md` | Pre-registered criteria and the appended result |
| `before_after/run_v7_test.py` | Harness: Claude Code as the agent, GNA tools over MCP, unmodified scorer (`geoagentbench/scoring.py`) |
| `before_after/results_before/`, `before_after/results_v7/` | Raw scored results; `results_before_posthoc_task_changes.jsonl` is the after run before the 3 task changes |
