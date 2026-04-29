"""Pipeline batch summary generator.

Reads all per-experiment _run_meta.json + results.jsonl files from a batch
output directory and produces:
  - _batch_summary.json  (the paper artifact — leaderboard, all metrics, all Q&A)
  - leaderboard.png      (cross-model comparison visual)
  - README.txt           (human-readable explanation)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def _load_jsonl(path: Path) -> List[dict]:
    """Load all records from a JSONL file."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _build_experiment_block(meta: dict, results: List[dict]) -> dict:
    """Build one experiment entry for the batch summary."""
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed

    # Aggregate tokens and cost
    total_input = sum(r.get("input_tokens", 0) for r in results)
    total_output = sum(r.get("output_tokens", 0) for r in results)
    total_cost = sum(r.get("cost_usd", 0) for r in results)
    total_duration = sum(r.get("duration_ms", 0) for r in results)

    # Partial credit averages
    check_scores = [r.get("check_score", 0) for r in results]
    quality_scores = [r.get("quality_check_score", 0) for r in results]
    kw_coverages = [r["keyword_coverage"] for r in results if r.get("keyword_coverage") is not None]
    tool_f1s = [r["tool_f1"] for r in results if r.get("tool_f1") is not None]
    ms_per_rounds = [r["ms_per_round"] for r in results if r.get("ms_per_round") is not None]

    def _safe_avg(vals):
        return round(sum(vals) / len(vals), 4) if vals else None

    # Accuracy by category
    cat_groups: Dict[str, dict] = {}
    diff_groups: Dict[str, dict] = {}
    error_counts: Dict[str, int] = {}
    fail_by_diff: Dict[str, int] = {}
    fail_by_cat: Dict[str, int] = {}

    for r in results:
        meta_field = r.get("metadata", {})
        cat = meta_field.get("category", "uncategorized")
        diff = meta_field.get("difficulty", "unknown")

        if cat not in cat_groups:
            cat_groups[cat] = {"total": 0, "passed": 0, "failed": 0}
        cat_groups[cat]["total"] += 1
        if r.get("passed"):
            cat_groups[cat]["passed"] += 1
        else:
            cat_groups[cat]["failed"] += 1

        if diff not in diff_groups:
            diff_groups[diff] = {"total": 0, "passed": 0}
        diff_groups[diff]["total"] += 1
        if r.get("passed"):
            diff_groups[diff]["passed"] += 1

        if not r.get("passed"):
            ec = r.get("error_category")
            if ec:
                error_counts[ec] = error_counts.get(ec, 0) + 1
            fail_by_diff[diff] = fail_by_diff.get(diff, 0) + 1
            fail_by_cat[cat] = fail_by_cat.get(cat, 0) + 1

    # Add pass_rate to category and difficulty groups
    for g in cat_groups.values():
        g["pass_rate"] = round(g["passed"] / g["total"], 4) if g["total"] else 0.0
    for g in diff_groups.values():
        g["pass_rate"] = round(g["passed"] / g["total"], 4) if g["total"] else 0.0

    # Check type accuracy
    check_type_totals: Dict[str, int] = {}
    check_type_passed: Dict[str, int] = {}
    for r in results:
        for c in r.get("checks", []):
            name = c.get("check", "")
            ctype = name.split(":")[0].split(" ")[0] if name else ""
            if not ctype:
                continue
            check_type_totals[ctype] = check_type_totals.get(ctype, 0) + 1
            if c.get("passed"):
                check_type_passed[ctype] = check_type_passed.get(ctype, 0) + 1
    check_type_acc = {
        k: round(check_type_passed.get(k, 0) / v, 3)
        for k, v in check_type_totals.items()
    }

    # Build per-case entries
    cases_out = []
    for r in results:
        meta_field = r.get("metadata", {})
        cases_out.append({
            "case_id": r.get("case_id", ""),
            "category": meta_field.get("category", ""),
            "difficulty": meta_field.get("difficulty", ""),
            "passed": r.get("passed", False),
            "question": r.get("question", ""),
            "answer": r.get("full_answer", r.get("answer_preview", "")),
            "tools_called": r.get("tools_called", []),
            "checks": r.get("checks", []),
            "metrics": {
                "duration_ms": r.get("duration_ms", 0),
                "rounds": r.get("rounds", 0),
                "cost_usd": r.get("cost_usd", 0),
                "input_tokens": r.get("input_tokens", 0),
                "output_tokens": r.get("output_tokens", 0),
                "check_score": r.get("check_score", 0),
                "keyword_coverage": r.get("keyword_coverage"),
                "tool_f1": r.get("tool_f1"),
            },
            "error": r.get("error"),
            "error_category": r.get("error_category"),
        })

    config = meta.get("config", {})

    return {
        "experiment_id": meta.get("experiment_id", ""),
        "run_id": meta.get("run_id", ""),
        "model_id": meta.get("model_id", ""),
        "status": meta.get("status", ""),
        "gcs_folder": f"{meta.get('experiment_id', '')}/",

        "config": config,

        "accuracy": {
            "passed": passed,
            "failed": failed,
            "total": total,
            "accuracy": round(passed / total, 4) if total else 0.0,
            "avg_check_score": _safe_avg(check_scores),
            "avg_quality_check_score": _safe_avg(quality_scores),
            "avg_keyword_coverage": _safe_avg(kw_coverages),
        },
        "accuracy_by_category": cat_groups,
        "accuracy_by_difficulty": diff_groups,
        "check_type_accuracy": check_type_acc,

        "cost_efficiency": {
            "total_cost_usd": round(total_cost, 4),
            "cost_per_case": round(total_cost / total, 4) if total else 0.0,
            "total_duration_ms": total_duration,
            "avg_ms_per_round": _safe_avg(ms_per_rounds),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
        },

        "error_analysis": {
            "error_taxonomy": error_counts,
            "failure_by_difficulty": fail_by_diff,
            "failure_by_category": fail_by_cat,
        },

        "cases": cases_out,
    }


def _build_leaderboard_entry(exp: dict) -> dict:
    """Extract leaderboard fields from an experiment block."""
    acc = exp.get("accuracy", {})
    cost = exp.get("cost_efficiency", {})
    return {
        "model_id": exp.get("model_id", ""),
        "experiment_id": exp.get("experiment_id", ""),
        "accuracy": acc.get("accuracy", 0),
        "avg_check_score": acc.get("avg_check_score"),
        "avg_keyword_coverage": acc.get("avg_keyword_coverage"),
        "cost_usd": cost.get("total_cost_usd", 0),
        "cost_per_case": cost.get("cost_per_case", 0),
        "total_duration_ms": cost.get("total_duration_ms", 0),
        "avg_ms_per_round": cost.get("avg_ms_per_round"),
        "total_tokens": cost.get("total_input_tokens", 0) + cost.get("total_output_tokens", 0),
    }


def generate_batch_summary(
    output_dir: str,
    batch_id: str = "",
    git_commit: str = "unknown",
    build_id: str = "",
) -> Optional[Path]:
    """Scan output_dir for experiment subfolders and generate the batch summary.

    Expected structure:
        output_dir/
            exp_001_.../
                _run_meta.json
                results.jsonl
            exp_002_.../
                ...

    Returns path to _batch_summary.json, or None if no experiments found.
    """
    root = Path(output_dir)
    if not root.exists():
        print(f"  Batch summary: output dir {root} does not exist.")
        return None

    experiments = []
    experiment_metas = []

    # Collect experiment dirs: either subfolders or the root itself (single-experiment case)
    candidate_dirs = []
    for subdir in sorted(root.iterdir()):
        if subdir.is_dir():
            candidate_dirs.append(subdir)

    # Fallback: check if root itself has _run_meta.json + results.jsonl (flat single-experiment)
    if not candidate_dirs or (root / "_run_meta.json").exists():
        if (root / "_run_meta.json").exists() and (root / "results.jsonl").exists():
            candidate_dirs = [root]

    for exp_dir in candidate_dirs:
        meta_path = exp_dir / "_run_meta.json"
        jsonl_path = exp_dir / "results.jsonl"

        if not meta_path.exists() or not jsonl_path.exists():
            continue

        with open(meta_path) as f:
            meta = json.load(f)
        results = _load_jsonl(jsonl_path)

        if not results:
            continue

        exp_block = _build_experiment_block(meta, results)
        experiments.append(exp_block)
        experiment_metas.append(meta)

    if not experiments:
        print("  Batch summary: no experiment subfolders with _run_meta.json + results.jsonl found.")
        return None

    # Build leaderboard sorted by accuracy (desc), then cost (asc)
    leaderboard = [_build_leaderboard_entry(e) for e in experiments]
    leaderboard.sort(key=lambda x: (-x["accuracy"], x["cost_usd"]))
    for i, entry in enumerate(leaderboard, 1):
        entry["rank"] = i

    # Resolve git commit from experiment metas if not provided
    if git_commit == "unknown":
        for m in experiment_metas:
            gc = m.get("git_commit", "unknown")
            if gc != "unknown":
                git_commit = gc
                break

    batch = {
        "batch_id": batch_id or os.environ.get("BUILD_ID", f"local_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "cloudbuild_build_id": build_id or os.environ.get("BUILD_ID", ""),
        "leaderboard": leaderboard,
        "experiments": experiments,
        "environment": experiment_metas[0].get("environment", {}) if experiment_metas else {},
    }

    summary_path = root / "_batch_summary.json"
    with open(summary_path, "w") as f:
        json.dump(batch, f, indent=2, ensure_ascii=False)

    print(f"  Batch summary: {summary_path} ({len(experiments)} experiments)")

    # Generate README.txt
    _write_readme(root, batch)

    # Generate leaderboard.png (non-fatal)
    _plot_leaderboard(root, leaderboard)

    return summary_path


def _write_readme(root: Path, batch: dict) -> None:
    """Write a human-readable README.txt at the batch root."""
    lines = [
        f"GeoNatureAgent Benchmark Batch Run: {batch['batch_id']}",
        f"Generated: {batch['timestamp']}",
        f"Git commit: {batch['git_commit']}",
        "",
        "Leaderboard",
        "-" * 60,
    ]
    for entry in batch.get("leaderboard", []):
        lines.append(
            f"  #{entry['rank']:2d}  {entry['accuracy']:.1%}  ${entry['cost_usd']:.4f}  {entry['model_id']}"
        )
    lines.extend([
        "",
        "Files",
        "-" * 60,
        "  _batch_summary.json  - Full results (paper artifact)",
        "  leaderboard.png      - Visual comparison",
        "  <experiment_id>/     - Per-model results",
        "",
    ])
    (root / "README.txt").write_text("\n".join(lines))


def _plot_leaderboard(root: Path, leaderboard: List[dict]) -> None:
    """Generate leaderboard.png bar chart. Non-fatal."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if not leaderboard:
            return

        models = [e.get("experiment_id", e.get("model_id", ""))[:30] for e in leaderboard]
        accuracies = [e["accuracy"] * 100 for e in leaderboard]
        costs = [e["cost_usd"] for e in leaderboard]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, max(5, len(models) * 0.5)))

        # Accuracy bar chart
        colors = ["#2ecc71" if a >= 60 else "#f39c12" if a >= 40 else "#e74c3c" for a in accuracies]
        ax1.barh(models, accuracies, color=colors)
        ax1.set_xlabel("Accuracy (%)")
        ax1.set_title("Model Accuracy")
        ax1.set_xlim(0, 100)
        for i, v in enumerate(accuracies):
            ax1.text(v + 1, i, f"{v:.1f}%", va="center", fontsize=9)

        # Cost bar chart
        ax2.barh(models, costs, color="#3498db")
        ax2.set_xlabel("Cost (USD)")
        ax2.set_title("Total Cost")
        for i, v in enumerate(costs):
            ax2.text(v + max(costs) * 0.02, i, f"${v:.4f}", va="center", fontsize=9)

        plt.tight_layout()
        fig.savefig(str(root / "leaderboard.png"), dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Leaderboard chart: {root / 'leaderboard.png'}")
    except Exception as exc:
        print(f"  WARNING: leaderboard chart failed (non-fatal): {exc}")


def main():
    """CLI entry point for batch summary generation."""
    parser = argparse.ArgumentParser(description="Generate batch summary from experiment outputs")
    parser.add_argument("output_dir", help="Root directory containing experiment subfolders")
    parser.add_argument("--batch-id", default="", help="Batch identifier (default: from BUILD_ID env)")
    parser.add_argument("--git-commit", default="unknown", help="Git commit hash")
    parser.add_argument("--build-id", default="", help="CloudBuild build ID")
    args = parser.parse_args()

    result = generate_batch_summary(
        output_dir=args.output_dir,
        batch_id=args.batch_id,
        git_commit=args.git_commit,
        build_id=args.build_id,
    )
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
