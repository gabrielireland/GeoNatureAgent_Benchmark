"""
Compile the paper's final benchmark numbers from raw GCS results.

Given a YAML config that maps each model's experiment_id to its Cloud Run
result directory in GCS, this script pulls every `results.jsonl`, aggregates
across the 3 seeds, and writes three artefacts to `paper/final_results/`:

  - leaderboard.csv      one row per model (mean ± std accuracy, cost, tokens)
  - per_category.csv     model × category mean accuracy
  - per_case.csv         every case × seed observation (the raw matrix)

The script is the single source of truth for every number reported in the
paper. To reproduce the paper's leaderboard from scratch:

    python scripts/compile_final_results.py \\
        --config paper/final_results/sources.yaml

Anyone can re-run with the same source config and get the same CSVs;
diff-checking against the committed CSVs verifies reproducibility.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / "paper" / "final_results" / "sources.yaml"
DEFAULT_OUT = REPO / "paper" / "final_results"


def gsutil_cat(uri: str) -> str:
    """Fetch a GCS object to memory. Errors out cleanly if missing."""
    r = subprocess.run(["gsutil", "cat", uri], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"gsutil cat failed for {uri}\n  stderr: {r.stderr.strip()}")
    return r.stdout


def load_results(
    bucket: str,
    run_dir: str,
    experiment_id: str,
    seeds: list[int] | None = None,
) -> list[dict]:
    """Load all per-case rows from a single experiment's results.jsonl.

    If `seeds` is given, only rows whose `seed` field appears in the list
    are returned; this lets the manifest restrict a model to a subset of
    seeds (e.g. when the provider does not implement deterministic seeding).
    """
    uri = f"gs://{bucket}/GeoNatureAgent/experiments/{run_dir}/{experiment_id}/results.jsonl"
    rows = []
    for line in gsutil_cat(uri).splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"empty results.jsonl: {uri}")
    if seeds is not None:
        allowed = set(seeds)
        rows = [r for r in rows if r.get("seed") in allowed]
        if not rows:
            raise SystemExit(f"no rows match seeds={seeds} in {uri}")
    return rows


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return (float("nan"), float("nan"))
    if len(values) == 1:
        return (values[0], 0.0)
    return (statistics.mean(values), statistics.stdev(values))


def _capability_passed(row: dict) -> bool:
    """Did the agent solve the case, ignoring the cost-budget gate?

    A case counts as a capability pass if (a) the runner marked it passed,
    or (b) every applicable check except ``max_cost_usd`` passed. We do not
    treat ``max_cost_usd`` as part of capability: the per-case cost budget
    is a deployment threshold, not a measure of reasoning ability. Cost is
    reported separately as a Pareto axis.
    """
    if row.get("passed"):
        return True
    checks = row.get("checks", [])
    if not checks:
        return False
    for c in checks:
        name = str(c.get("check", ""))
        # Skip the cost-budget check; require all others to pass.
        if name == "max_cost_usd" or name.startswith("cost"):
            continue
        if not c.get("passed"):
            return False
    return True


def aggregate_model(model_name: str, rows: list[dict]) -> dict:
    """Compute per-seed metrics and mean ± std across seeds for one model."""
    by_seed = collections.defaultdict(list)
    for r in rows:
        by_seed[r.get("seed")].append(r)

    per_seed_accuracy = []
    per_seed_cost = []
    per_seed_tokens = []
    per_seed_check = []
    per_seed_kw = []

    for seed, seed_rows in by_seed.items():
        n = len(seed_rows)
        passed = sum(1 for r in seed_rows if _capability_passed(r))
        per_seed_accuracy.append(passed / n)
        per_seed_cost.append(sum(r.get("cost_usd") or 0 for r in seed_rows))
        per_seed_tokens.append(
            sum((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in seed_rows)
        )
        per_seed_check.append(
            sum(r.get("check_score") or 0 for r in seed_rows) / n
        )
        per_seed_kw.append(
            sum(r.get("keyword_coverage") or 0 for r in seed_rows) / n
        )

    acc_mean, acc_std = mean_std(per_seed_accuracy)
    cost_mean, cost_std = mean_std(per_seed_cost)
    tok_mean, tok_std = mean_std(per_seed_tokens)
    check_mean, check_std = mean_std(per_seed_check)
    kw_mean, kw_std = mean_std(per_seed_kw)

    seeds_sorted = sorted(by_seed.keys(), key=lambda s: (s is None, s))

    return {
        "model": model_name,
        "n_seeds": len(by_seed),
        "seeds": seeds_sorted,
        "n_cases_per_seed": len(rows) // max(len(by_seed), 1),
        "accuracy_mean": acc_mean,
        "accuracy_std": acc_std,
        "accuracy_per_seed": per_seed_accuracy,
        "cost_mean": cost_mean,
        "cost_std": cost_std,
        "cost_per_case": cost_mean / (len(rows) / max(len(by_seed), 1)) if rows else 0.0,
        "tokens_mean": tok_mean,
        "tokens_std": tok_std,
        "check_score_mean": check_mean,
        "check_score_std": check_std,
        "keyword_coverage_mean": kw_mean,
        "keyword_coverage_std": kw_std,
    }


def category_breakdown(rows: list[dict]) -> dict[str, float]:
    """Mean accuracy per category, averaged across seeds."""
    by_cat = collections.defaultdict(list)
    for r in rows:
        cat = (r.get("metadata") or {}).get("category")
        if cat:
            by_cat[cat].append(1 if _capability_passed(r) else 0)
    return {cat: sum(v) / len(v) for cat, v in by_cat.items()}


def write_leaderboard(out_path: Path, model_aggs: list[dict]) -> None:
    fieldnames = [
        "model", "experiment_id", "accuracy_mean", "accuracy_std",
        "accuracy_seed_42", "accuracy_seed_1337", "accuracy_seed_2024",
        "cost_per_seed_mean", "cost_per_case", "tokens_per_seed_mean",
        "check_score_mean", "keyword_coverage_mean", "n_seeds", "n_cases_per_seed",
    ]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for m in sorted(model_aggs, key=lambda x: -x["accuracy_mean"]):
            seeds = {s: a for s, a in zip(m["seeds"], m["accuracy_per_seed"])}
            w.writerow({
                "model": m["model"],
                "experiment_id": m["experiment_id"],
                "accuracy_mean": f"{m['accuracy_mean']:.4f}",
                "accuracy_std": f"{m['accuracy_std']:.4f}",
                "accuracy_seed_42": f"{seeds.get(42, ''):.4f}" if 42 in seeds else "",
                "accuracy_seed_1337": f"{seeds.get(1337, ''):.4f}" if 1337 in seeds else "",
                "accuracy_seed_2024": f"{seeds.get(2024, ''):.4f}" if 2024 in seeds else "",
                "cost_per_seed_mean": f"{m['cost_mean']:.4f}",
                "cost_per_case": f"{m['cost_per_case']:.5f}",
                "tokens_per_seed_mean": f"{m['tokens_mean']:.0f}",
                "check_score_mean": f"{m['check_score_mean']:.4f}",
                "keyword_coverage_mean": f"{m['keyword_coverage_mean']:.4f}",
                "n_seeds": m["n_seeds"],
                "n_cases_per_seed": m["n_cases_per_seed"],
            })


def write_per_category(out_path: Path, model_cats: dict[str, dict[str, float]]) -> None:
    all_cats = sorted({c for cats in model_cats.values() for c in cats})
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model"] + all_cats)
        for model, cats in model_cats.items():
            w.writerow([model] + [f"{cats.get(c, 0):.4f}" for c in all_cats])


def write_per_case(out_path: Path, all_rows: list[tuple[str, dict]]) -> None:
    fieldnames = [
        "model", "experiment_id", "case_id", "seed", "category", "passed",
        "passed_with_cost_gate",
        "check_score", "quality_check_score", "keyword_coverage",
        "cost_usd", "input_tokens", "output_tokens", "rounds", "duration_ms",
        "error_category",
    ]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for model, r in all_rows:
            w.writerow({
                "model": model,
                "experiment_id": r.get("experiment_id"),
                "case_id": r.get("case_id"),
                "seed": r.get("seed"),
                "category": (r.get("metadata") or {}).get("category"),
                "passed": int(_capability_passed(r)),
                "passed_with_cost_gate": int(bool(r.get("passed"))),
                "check_score": r.get("check_score"),
                "quality_check_score": r.get("quality_check_score"),
                "keyword_coverage": r.get("keyword_coverage"),
                "cost_usd": r.get("cost_usd"),
                "input_tokens": r.get("input_tokens"),
                "output_tokens": r.get("output_tokens"),
                "rounds": r.get("rounds"),
                "duration_ms": r.get("duration_ms"),
                "error_category": r.get("error_category"),
            })


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    config = yaml.safe_load(args.config.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)

    bucket = config["bucket"]
    models = config["models"]  # dict: display_name -> {experiment_id, run_dir}

    print(f"Compiling final results from {len(models)} models in gs://{bucket}/")
    print(f"  config: {args.config}")
    print(f"  output: {args.out_dir}/\n")

    model_aggs = []
    model_cats = {}
    all_rows = []
    for display_name, spec in models.items():
        exp_id = spec["experiment_id"]
        run_dir = spec["run_dir"]
        seed_filter = spec.get("seeds")
        seed_note = f" (seeds={seed_filter})" if seed_filter else ""
        print(f"  [{display_name}] {run_dir}/{exp_id}/{seed_note}")
        rows = load_results(bucket, run_dir, exp_id, seeds=seed_filter)
        agg = aggregate_model(display_name, rows)
        agg["experiment_id"] = exp_id
        agg["run_dir"] = run_dir
        model_aggs.append(agg)
        model_cats[display_name] = category_breakdown(rows)
        for r in rows:
            all_rows.append((display_name, r))
        print(f"    {len(rows):4d} rows | {agg['n_seeds']} seeds | "
              f"accuracy {agg['accuracy_mean']*100:.1f}% ± {agg['accuracy_std']*100:.1f}%")

    leaderboard_path = args.out_dir / "leaderboard.csv"
    per_category_path = args.out_dir / "per_category.csv"
    per_case_path = args.out_dir / "per_case.csv"

    write_leaderboard(leaderboard_path, model_aggs)
    write_per_category(per_category_path, model_cats)
    write_per_case(per_case_path, all_rows)

    print(f"\nWrote:")
    print(f"  {leaderboard_path.relative_to(REPO)}  ({len(model_aggs)} rows)")
    print(f"  {per_category_path.relative_to(REPO)}  ({len(model_cats)} rows)")
    print(f"  {per_case_path.relative_to(REPO)}  ({len(all_rows)} rows)")


if __name__ == "__main__":
    main()
