"""Fold the two extra v5 models (GPT-4o, Gemma-3-27B) into the paper database.

They were run on the full 93-case v5 suite (results/run_{gpt4o,gemma3}_openrouter_v5/)
but never compiled into leaderboard.csv / per_category.csv, so they were missing
from every v5 figure. This computes their rows with the EXACT same functions the
7 paper models were compiled with (scripts/compile_final_results.py) and merges
them in, re-sorting by accuracy. Idempotent: replaces any existing row for these
models rather than duplicating.

    python3 scripts/add_models_to_leaderboard.py
    python3 paper/generate_figures.py      # then regenerate all v5 figures
"""
import csv
import json
import pathlib

import scripts.compile_final_results as C  # reuse the canonical metric definitions

ROOT = pathlib.Path(__file__).resolve().parents[1]
RES = ROOT / "paper" / "final_results"

NEW = [
    ("GPT-4o", "exp_043_gpt4o_openrouter_v5", ROOT / "results/run_gpt4o_openrouter_v5/results.jsonl"),
    ("Gemma-3-27B", "exp_044_gemma3_openrouter_v5", ROOT / "results/run_gemma3_openrouter_v5/results.jsonl"),
]

LB_COLS = ["model", "experiment_id", "accuracy_mean", "accuracy_std",
           "accuracy_seed_42", "accuracy_seed_1337", "accuracy_seed_2024",
           "cost_per_seed_mean", "cost_per_case", "tokens_per_seed_mean",
           "check_score_mean", "keyword_coverage_mean", "n_seeds", "n_cases_per_seed"]


def load_rows(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def lb_row(name, exp_id, agg):
    seeds = {s: a for s, a in zip(agg["seeds"], agg["accuracy_per_seed"])}
    return {
        "model": name, "experiment_id": exp_id,
        "accuracy_mean": f"{agg['accuracy_mean']:.4f}",
        "accuracy_std": f"{agg['accuracy_std']:.4f}",
        "accuracy_seed_42": f"{seeds.get(42, ''):.4f}" if 42 in seeds else "",
        "accuracy_seed_1337": f"{seeds.get(1337, ''):.4f}" if 1337 in seeds else "",
        "accuracy_seed_2024": f"{seeds.get(2024, ''):.4f}" if 2024 in seeds else "",
        "cost_per_seed_mean": f"{agg['cost_mean']:.4f}",
        "cost_per_case": f"{agg['cost_per_case']:.5f}",
        "tokens_per_seed_mean": f"{agg['tokens_mean']:.0f}",
        "check_score_mean": f"{agg['check_score_mean']:.4f}",
        "keyword_coverage_mean": f"{agg['keyword_coverage_mean']:.4f}",
        "n_seeds": agg["n_seeds"], "n_cases_per_seed": agg["n_cases_per_seed"],
    }


def main():
    # ---- leaderboard.csv ----
    lb_path = RES / "leaderboard.csv"
    existing = list(csv.DictReader(lb_path.open()))
    new_names = {n for n, _, _ in NEW}
    kept = [r for r in existing if r["model"] not in new_names]

    cat_rows = {}  # for per_category.csv
    for name, exp_id, path in NEW:
        rows = load_rows(path)
        agg = C.aggregate_model(name, rows)
        kept.append(lb_row(name, exp_id, agg))
        # category_breakdown reads metadata.category; v5 rows carry it
        cat_rows[name] = C.category_breakdown(rows)
        print(f"  {name}: acc={agg['accuracy_mean']:.4f}±{agg['accuracy_std']:.4f} "
              f"cost/seed=${agg['cost_mean']:.2f} cost/case=${agg['cost_per_case']:.5f} "
              f"tokens/seed={agg['tokens_mean']:.0f} n_seeds={agg['n_seeds']}")

    kept.sort(key=lambda r: -float(r["accuracy_mean"]))
    with lb_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LB_COLS)
        w.writeheader()
        w.writerows(kept)
    print(f"wrote {lb_path} ({len(kept)} models)")

    # ---- per_category.csv ----
    pc_path = RES / "per_category.csv"
    pc_existing = list(csv.DictReader(pc_path.open()))
    cats = [c for c in pc_existing[0].keys() if c != "model"] if pc_existing else []
    pc_kept = [r for r in pc_existing if r["model"] not in new_names]
    for name, _, _ in NEW:
        cb = cat_rows[name]
        row = {"model": name}
        for c in cats:
            row[c] = f"{cb[c]:.4f}" if c in cb else ""
        pc_kept.append(row)
    # keep same model order as leaderboard
    order = {r["model"]: i for i, r in enumerate(kept)}
    pc_kept.sort(key=lambda r: order.get(r["model"], 999))
    with pc_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["model"] + cats)
        w.writeheader()
        w.writerows(pc_kept)
    print(f"wrote {pc_path} ({len(pc_kept)} models)")


if __name__ == "__main__":
    main()
