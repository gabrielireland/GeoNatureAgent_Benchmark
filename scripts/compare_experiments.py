#!/usr/bin/env python3
"""Compare GeoNatureAgent benchmark results across multiple experiments or models.

Reads two or more benchmark JSONL files (one per experiment/model) and generates
a side-by-side comparison dashboard PNG.

Usage:
    python scripts/compare_experiments.py results/exp_003.jsonl results/exp_004.jsonl
    python scripts/compare_experiments.py *.jsonl --out comparison.png
    python scripts/compare_experiments.py *.jsonl --group-by model_id --out comparison.png

Callable from runner.py:
    from scripts.compare_experiments import generate_comparison
    generate_comparison(paths, "/tmp/output/comparison_report.png")
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

from scripts.visualize_benchmark import (
    load_benchmark_jsonl,
    _build_check_type_rates,
    _CHECK_PREFIXES,
    _spines_off,
    _short,
    BLUE, GREEN, ORANGE, RED, PURPLE, TEAL, GREY,
)


CAT_PALETTE = [BLUE, ORANGE, GREEN, RED, PURPLE, TEAL, "#937860", "#DA8BC3"]


# ── data helpers ──────────────────────────────────────────────────────────────

def _partition_by(records: list[dict], field: str) -> dict[str, list[dict]]:
    """Group records by a metadata field value."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        key = r.get(field) or "unknown"
        groups[key].append(r)
    return dict(groups)


def _group_label(key: str) -> str:
    """Shorten a group key for display."""
    return _short(key.replace("vertex_ai/", ""), 28)


def _group_stats(group: list[dict]) -> dict:
    n = len(group)
    if n == 0:
        return {"n": 0, "acc": 0.0, "check_score": 0.0, "quality_check_score": 0.0,
                "cost_usd": 0.0, "tool_precision": 0.0, "tool_recall": 0.0, "tool_f1": 0.0,
                "git_commit": "unknown", "model_id": "unknown", "experiment_id": "unknown"}
    acc = sum(1 for r in group if r.get("passed")) / n
    cs = float(np.mean([r.get("check_score", 1.0) for r in group]))
    qcs = float(np.mean([r.get("quality_check_score", 1.0) for r in group]))
    cost = float(np.mean([r.get("cost_usd", 0.0) for r in group]))
    tp = float(np.mean([r.get("tool_precision") or 0.0 for r in group]))
    tr = float(np.mean([r.get("tool_recall") or 0.0 for r in group]))
    tf1 = float(np.mean([r.get("tool_f1") or 0.0 for r in group]))
    git = group[0].get("git_commit", "unknown")
    model = group[0].get("model_id", "unknown")
    exp = group[0].get("experiment_id", "unknown")
    return {"n": n, "acc": acc, "check_score": cs, "quality_check_score": qcs,
            "cost_usd": cost, "tool_precision": tp, "tool_recall": tr, "tool_f1": tf1,
            "git_commit": git, "model_id": model, "experiment_id": exp}


# ── panels ────────────────────────────────────────────────────────────────────

def _draw_accuracy_bars(ax, groups: dict[str, list[dict]]) -> None:
    labels = list(groups.keys())
    stats = [_group_stats(groups[k]) for k in labels]
    x = np.arange(len(labels))
    w = 0.35
    accs = [s["acc"] for s in stats]
    css = [s["check_score"] for s in stats]
    bars_acc = ax.bar(x - w / 2, accs, width=w, color=GREEN, alpha=0.85, label="binary acc")
    bars_cs = ax.bar(x + w / 2, css, width=w, color=BLUE, alpha=0.85, label="avg check_score")
    ax.set_xticks(x)
    ax.set_xticklabels([_group_label(k) for k in labels], rotation=20, ha="right", fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.axhline(1.0, color=GREY, lw=0.8, ls="--")
    ax.set_title("Accuracy by experiment", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    for bar, val in [(b, v) for b, v in zip(bars_acc, accs)] + [(b, v) for b, v in zip(bars_cs, css)]:
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.02, f"{val:.2f}",
                ha="center", fontsize=7)
    # Overlay quality_check_score as diamond markers
    qcs = [s["quality_check_score"] for s in stats]
    ax.scatter(x + w / 2, qcs, marker="D", color=TEAL, zorder=5, s=30, label="quality_check_score")
    ax.legend(fontsize=7)
    _spines_off(ax)


def _draw_cost_bars(ax, groups: dict[str, list[dict]]) -> None:
    labels = list(groups.keys())
    stats = [_group_stats(groups[k]) for k in labels]
    costs = [s["cost_usd"] for s in stats]
    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(labels))]
    bars = ax.barh([_group_label(k) for k in labels], costs, color=colors, alpha=0.85)
    for bar, val in zip(bars, costs):
        ax.text(val + max(costs) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"${val:.4f}", va="center", fontsize=8)
    ax.set_xlabel("Avg cost per case (USD)", fontsize=8)
    ax.set_title("Cost per case", fontsize=10, fontweight="bold")
    _spines_off(ax)


def _draw_check_type_heatmap(ax, groups: dict[str, list[dict]]) -> None:
    import matplotlib.colors as mcolors

    check_keys = [key for _, key in _CHECK_PREFIXES]
    group_labels = [_group_label(k) for k in groups.keys()]
    matrix = np.zeros((len(check_keys), len(group_labels)))

    for j, (gkey, recs) in enumerate(groups.items()):
        rates = _build_check_type_rates(recs)
        for i, ck in enumerate(check_keys):
            matrix[i, j] = rates.get(ck, float("nan"))

    cmap = mcolors.LinearSegmentedColormap.from_list("rg", [RED, ORANGE, GREEN])
    im = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0.0, vmax=1.0, interpolation="none")
    ax.set_xticks(range(len(group_labels)))
    ax.set_xticklabels(group_labels, rotation=20, ha="right", fontsize=8)
    ax.set_yticks(range(len(check_keys)))
    ax.set_yticklabels(check_keys, fontsize=8)
    for i in range(len(check_keys)):
        for j in range(len(group_labels)):
            val = matrix[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if val < 0.5 else "black")
    plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    ax.set_title("Check-type pass rate", fontsize=10, fontweight="bold")


def _draw_tool_f1_bars(ax, groups: dict[str, list[dict]]) -> None:
    labels = list(groups.keys())
    stats = [_group_stats(groups[k]) for k in labels]
    x = np.arange(len(labels))
    w = 0.25
    ax.bar(x - w, [s["tool_precision"] for s in stats], width=w, color=BLUE, alpha=0.85, label="precision")
    ax.bar(x, [s["tool_recall"] for s in stats], width=w, color=GREEN, alpha=0.85, label="recall")
    ax.bar(x + w, [s["tool_f1"] for s in stats], width=w, color=ORANGE, alpha=0.85, label="F1")
    ax.set_xticks(x)
    ax.set_xticklabels([_group_label(k) for k in labels], rotation=20, ha="right", fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.set_title("Tool F1 by experiment", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    _spines_off(ax)


def _draw_accuracy_cost_scatter(ax, groups: dict[str, list[dict]]) -> None:
    labels = list(groups.keys())
    stats = [_group_stats(groups[k]) for k in labels]
    costs = [s["cost_usd"] for s in stats]
    accs = [s["acc"] for s in stats]
    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(labels))]

    # Identify Pareto-optimal points (higher acc, lower cost)
    pareto = []
    for i, (c, a) in enumerate(zip(costs, accs)):
        dominated = any(
            costs[j] <= c and accs[j] >= a and (costs[j] < c or accs[j] > a)
            for j in range(len(labels)) if j != i
        )
        pareto.append(not dominated)

    for i, (c, a) in enumerate(zip(costs, accs)):
        marker = "*" if pareto[i] else "o"
        size = 120 if pareto[i] else 60
        ax.scatter(c, a, color=colors[i], marker=marker, s=size, zorder=5)
        ax.annotate(_group_label(labels[i]), (c, a),
                    textcoords="offset points", xytext=(5, 3), fontsize=7)

    ax.set_xlabel("Avg cost per case (USD)", fontsize=8)
    ax.set_ylabel("Binary accuracy", fontsize=8)
    ax.set_ylim(0, 1.1)
    ax.set_title("Accuracy vs cost  (★ = Pareto-optimal)", fontsize=10, fontweight="bold")
    _spines_off(ax)


def _draw_summary_table(ax, groups: dict[str, list[dict]]) -> None:
    ax.axis("off")
    lines = ["experiment / model                   n    acc   check  cost/case  git"]
    lines.append("─" * 72)
    for key, recs in groups.items():
        s = _group_stats(recs)
        exp = _short(s["experiment_id"], 20)
        model = _short(s["model_id"].replace("vertex_ai/", ""), 18)
        lines.append(
            f"{exp:<20}  {model:<18}  {s['n']:>3}  {s['acc']:.2f}  "
            f"{s['check_score']:.2f}  ${s['cost_usd']:.4f}  {s['git_commit']}"
        )
    ax.text(0.02, 0.95, "\n".join(lines), transform=ax.transAxes,
            fontsize=7, va="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#F8F8F8", edgecolor=GREY, alpha=0.8))
    ax.set_title("Summary", fontsize=10, fontweight="bold")


# ── figure builder ────────────────────────────────────────────────────────────

def _build_comparison_figure(groups: dict[str, list[dict]]) -> plt.Figure:
    """Build the 3×3 comparison dashboard."""
    n_groups = len(groups)
    total_cases = sum(len(v) for v in groups.values())

    fig = plt.figure(figsize=(20, 18))
    fig.suptitle(
        f"GeoAgentBench — Experiment Comparison  ({n_groups} experiments, {total_cases} total cases)",
        fontsize=14, fontweight="bold", y=0.99,
    )
    gs = gridspec.GridSpec(
        3, 3, figure=fig,
        hspace=0.55, wspace=0.38,
        left=0.07, right=0.97,
        top=0.955, bottom=0.05,
    )

    # Row 0 — accuracy, cost
    _draw_accuracy_bars(fig.add_subplot(gs[0, 0]), groups)
    _draw_cost_bars(fig.add_subplot(gs[0, 1]), groups)
    ax_empty = fig.add_subplot(gs[0, 2])
    ax_empty.axis("off")  # reserved — summary table spans row 2

    # Row 1 — check-type heatmap (full width)
    _draw_check_type_heatmap(fig.add_subplot(gs[1, :]), groups)

    # Row 2 — tool F1, scatter, summary table
    _draw_tool_f1_bars(fig.add_subplot(gs[2, 0]), groups)
    _draw_accuracy_cost_scatter(fig.add_subplot(gs[2, 1]), groups)
    _draw_summary_table(fig.add_subplot(gs[2, 2]), groups)

    return fig


# ── public API ────────────────────────────────────────────────────────────────

def generate_comparison(
    paths: list[Path],
    output_path: str,
    group_by: str = "experiment_id",
) -> None:
    """Generate and save a comparison dashboard PNG.

    Args:
        paths: Two or more benchmark JSONL files.
        output_path: Destination PNG path.
        group_by: Field to partition records by ('experiment_id' or 'model_id').
    """
    records = load_benchmark_jsonl(paths)
    if not records:
        return
    groups = _partition_by(records, group_by)
    if len(groups) < 2:
        return
    fig = _build_comparison_figure(groups)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="Two or more benchmark JSONL files")
    parser.add_argument("--out", default="", help="Save figure to this path instead of showing")
    parser.add_argument(
        "--group-by",
        choices=["experiment_id", "model_id"],
        default="experiment_id",
        dest="group_by",
        help="Field to use as the comparison axis (default: experiment_id)",
    )
    args = parser.parse_args()

    if len(args.files) < 2:
        print("compare_experiments.py requires at least 2 JSONL files.", file=sys.stderr)
        sys.exit(1)

    paths = [Path(p) for p in args.files]
    records = load_benchmark_jsonl(paths)
    if not records:
        print("No benchmark records found.", file=sys.stderr)
        sys.exit(1)

    groups = _partition_by(records, args.group_by)
    if len(groups) < 2:
        print(
            f"Only found 1 group when partitioning by '{args.group_by}'. "
            "Pass files from different experiments, or use --group-by model_id.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Loaded {len(records)} records across {len(groups)} groups: {list(groups.keys())}")

    fig = _build_comparison_figure(groups)

    if args.out:
        fig.savefig(args.out, dpi=150, bbox_inches="tight")
        print(f"Saved to {args.out}")
    else:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
