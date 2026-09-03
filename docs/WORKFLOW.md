# Benchmark lifecycle & provenance (compliance view)

How a task travels from JSON to a number in the paper, and what makes every
number traceable back to the run that produced it. GitHub renders the diagram.

```mermaid
flowchart TD
    subgraph DEFINE["1 · Define"]
        A["Task JSON<br/>geoagentbench/cases/&lt;set&gt;.json<br/>(query, expected_tools, must_contain,<br/>ground_truth, max_rounds, budget)"]
        B["Register set<br/>case_loader.py CASE_SETS<br/>('v5', 'v6', ...)"]
        A --> B
    end

    subgraph CONFIGURE["2 · Configure"]
        C["Experiment YAML<br/>benchmark/experiments/*.yaml<br/>(model_id, seeds {42,1337,2024},<br/>prompt_version v3, case_set)"]
    end

    subgraph RUN["3 · Run"]
        D["python -m geoagentbench --experiment ...<br/>ReAct loop against the 16-tool layer<br/>(same tools as the MCP server & API)"]
        E["results/run_*/results.jsonl<br/>ONE ROW PER case × seed, carrying:<br/>case_id · seed · experiment_id · model_id ·<br/>prompt_version · git_commit · checks · cost ·<br/>tokens · full conversation_trace"]
        D --> E
    end

    subgraph SCORE["4 · Score & aggregate (deterministic, no LLM judge)"]
        F["scoring.py — 8 checks,<br/>capability = pass or budget/round-gate excusal"]
        G["Aggregators:<br/>compile_final_results.py (v5, via sources.yaml)<br/>add_models_to_leaderboard.py (new models)<br/>aggregate_v6.py (expansion)<br/>aggregate_combined.py (103-task combined)"]
        F --> G
    end

    subgraph TRUTH["5 · Committed source of truth"]
        H["paper/final_results/*.csv + v6_table.tex<br/>leaderboard · per_category · per_case ·<br/>leaderboard_v6 · leaderboard_v5plus6 · sources.yaml<br/>(every paper number lives here, in git)"]
    end

    subgraph PUBLISH["6 · Publish"]
        I["Figures<br/>generate_figures.py · generate_v6_figure.py"]
        J["Paper<br/>tex \\input's the generated table;<br/>build script re-verifies content landed in the PDF"]
        K["Releases<br/>hf_dataset (prepare_hf_dataset.py) ·<br/>Zenodo versions (concept DOI stable)"]
    end

    B --> C --> D
    E --> F
    G --> H
    H --> I --> J
    H --> K
```

## The provenance chain (why any number is auditable)

1. **Row level** — every `results.jsonl` row records its `case_id`, `seed`,
   `experiment_id`, `model_id`, `prompt_version`, the **`git_commit`** of the
   harness that produced it, and the full conversation trace. A leaderboard
   cell can be traced to the exact run rows that produced it.
2. **Manifest level** — `paper/final_results/sources.yaml` maps each model's
   leaderboard entry to its specific run output directory.
3. **Artifact level** — the aggregators emit CSVs (and the drop-in
   `v6_table.tex`) that are **committed**; the paper `\input`s the generated
   table rather than retyping numbers, so paper ↔ CSV drift is impossible for
   tables and grep-auditable for prose.
4. **Scoring level** — the scorer is deterministic (8 rule-based checks, no
   LLM-as-judge), so re-scoring stored traces reproduces the same outcomes.

## Adding new tasks — the checklist

1. Add cases to a JSON set in `geoagentbench/cases/` (new file for a new
   version, e.g. `benchmark_v7.json`; never mutate a published set — published
   sets are frozen instruments).
2. Register the set name in `case_loader.py` (one line).
3. Clone experiment YAMLs pointing `case_set` at it; run all models × 3 seeds.
4. Aggregate: extend/reuse the scripts in `scripts/` so results land as
   committed CSVs under `paper/final_results/` — **a run that isn't aggregated
   into a committed CSV is invisible** (this bit us once: two models had full
   runs but were missing from the leaderboard for months).
5. Report the new set **both** separately **and** in the combined suite metric
   (`python3 -m scripts.aggregate_combined`), as done for v6 → the 103-task
   leaderboard.
6. Regenerate figures, `\input` the fresh table, rebuild the paper, and verify
   the new content is literally present in the PDF before calling it done.

## Versioning rules

- Published task sets are immutable; growth happens by adding a new set
  (v6, v7, …) so previously reported numbers stay reproducible forever.
- Headline metrics name their denominator explicitly ("93-task main suite",
  "combined 103 tasks") — never a bare percentage.
- Zenodo releases use one **concept DOI** (always resolves to latest) plus
  per-version DOIs; new data = new Zenodo version, never an edit in place.
