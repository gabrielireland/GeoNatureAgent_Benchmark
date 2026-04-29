#!/usr/bin/env python3
"""Visualize GeoNatureAgent benchmark results from JSONL files.

Reads benchmark JSONL output from BenchmarkLogger (NOT production query logs).
Each line must be a ScoredResult record written by geoagentbench/logging_structured.py.

Usage:
    python scripts/visualize_benchmark.py                      # auto-glob results/*.jsonl
    python scripts/visualize_benchmark.py results/my.jsonl     # specific file(s)
    python scripts/visualize_benchmark.py --out report.png     # save instead of show

Callable from runner.py:
    from scripts.visualize_benchmark import plot_benchmark
    plot_benchmark(records, "/tmp/output/benchmark_report.png")
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # non-interactive backend for Cloud Run / headless containers
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np


# ── palette ──────────────────────────────────────────────────────────────────
BLUE   = "#4C72B0"
GREEN  = "#55A868"
ORANGE = "#DD8452"
RED    = "#C44E52"
PURPLE = "#8172B3"
TEAL   = "#64B5CD"
GREY   = "#AAAAAA"

DIFF_COLORS = {"easy": GREEN, "medium": ORANGE, "hard": RED, "unknown": GREY}
CAT_PALETTE = [BLUE, ORANGE, GREEN, RED, PURPLE, TEAL, "#937860", "#DA8BC3"]

# Check-type prefix → display key mapping (module-level to avoid duplication)
_CHECK_PREFIXES = [
    ("expected_tools",   "expected_tools"),
    ("chart_generated",  "chart_generated"),
    ("numeric_accuracy", "numeric_accuracy"),
    ("must_contain",     "must_contain"),
    ("must_not_contain", "must_not_contain"),
    ("max_rounds",       "max_rounds"),
    ("cost",             "cost_budget"),
    ("latency",          "latency_budget"),
    ("expected_actions", "expected_actions"),
]


# ── data helpers ─────────────────────────────────────────────────────────────

def load_benchmark_jsonl(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        with p.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "case_id" in obj and "event" not in obj:
                        records.append(obj)
                except json.JSONDecodeError:
                    pass
    return records


def _build_check_type_rates(records: list[dict]) -> dict[str, float]:
    """Pass rate per check type across all cases."""
    totals: dict[str, int] = {}
    passed_counts: dict[str, int] = {}
    for r in records:
        for c in (r.get("checks") or []):
            name = c.get("check", "")
            for prefix, key in _CHECK_PREFIXES:
                if name == prefix or name.startswith(f"{prefix}:") or name.startswith(f"{prefix} "):
                    totals[key] = totals.get(key, 0) + 1
                    if c.get("passed"):
                        passed_counts[key] = passed_counts.get(key, 0) + 1
                    break
    return {k: passed_counts.get(k, 0) / v for k, v in totals.items()}


def _aggregate_by_group(records: list[dict], group_field: str) -> dict[str, dict]:
    """Aggregate pass rate and check_score by a metadata field (difficulty or category)."""
    groups: dict[str, dict] = defaultdict(lambda: {"pass": 0, "fail": 0, "cs": []})
    for r in records:
        val = (r.get("metadata") or {}).get(group_field, "") or "unknown"
        groups[val]["pass" if r.get("passed") else "fail"] += 1
        groups[val]["cs"].append(r.get("check_score", 1.0))
    return dict(groups)


def _short(label: str, n: int = 20) -> str:
    return label[:n] + ("…" if len(label) > n else "")


def _spines_off(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)


def _short_ids(records: list[dict]) -> list[str]:
    return [_short(r.get("case_id", f"case_{i}"), 22) for i, r in enumerate(records)]


# ── drawing functions — one per subplot ──────────────────────────────────────

def _draw_accuracy_overview(ax, records: list[dict]) -> None:
    n = len(records)
    n_pass = sum(1 for r in records if r.get("passed"))
    binary_rate = n_pass / n
    avg_cs = np.mean([r.get("check_score", 1.0) for r in records])
    avg_qs = np.mean([r.get("quality_check_score", 1.0) for r in records])
    bars = ax.bar(
        ["Binary\naccuracy", "Avg check\nscore", "Avg quality\ncheck score"],
        [binary_rate, avg_cs, avg_qs],
        color=[GREEN if binary_rate >= 0.7 else ORANGE, BLUE, PURPLE],
        alpha=0.85, width=0.5,
    )
    ax.set_ylim(0, 1.1)
    ax.axhline(1.0, color=GREY, lw=0.8, ls="--")
    ax.set_title("Accuracy: binary vs partial credit", fontsize=10, fontweight="bold")
    ax.set_ylabel("score (0–1)", fontsize=8)
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{bar.get_height():.2f}", ha="center", fontsize=9, fontweight="bold")
    _spines_off(ax)


def _draw_difficulty_accuracy(ax, records: list[dict]) -> None:
    groups = _aggregate_by_group(records, "difficulty")
    diff_order = ["easy", "medium", "hard", "unknown"]
    present = [d for d in diff_order if d in groups]
    if not present:
        ax.set_visible(False)
        return
    pass_rates = [groups[d]["pass"] / (groups[d]["pass"] + groups[d]["fail"]) for d in present]
    cs_means = [np.mean(groups[d]["cs"]) for d in present]
    x = np.arange(len(present))
    ax.bar(x, pass_rates, color=[DIFF_COLORS[d] for d in present], alpha=0.8, label="pass rate")
    ax.plot(x, cs_means, "o--", color=BLUE, lw=1.5, ms=6, label="avg check_score")
    ax.set_xticks(x)
    ax.set_xticklabels(present, fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_title("Accuracy by difficulty", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    _spines_off(ax)


def _draw_summary_box(ax, records: list[dict]) -> None:
    ax.axis("off")
    n = len(records)
    n_pass = sum(1 for r in records if r.get("passed"))
    model_ids = list({r.get("model_id", "") for r in records if r.get("model_id")})

    cs_vals    = [r.get("check_score", 1.0) for r in records]
    qs_vals    = [r.get("quality_check_score", 1.0) for r in records]
    f1_vals    = [r.get("tool_f1") for r in records if r.get("tool_f1") is not None]
    af1_vals   = [r.get("action_f1") for r in records if r.get("action_f1") is not None]
    kw_vals    = [r.get("keyword_coverage") for r in records if r.get("keyword_coverage") is not None]
    mpr_vals   = [r.get("ms_per_round") for r in records if r.get("ms_per_round") is not None]
    ru_vals    = [r.get("rounds_utilization") for r in records if r.get("rounds_utilization") is not None]
    cu_vals    = [r.get("cost_utilization") for r in records if r.get("cost_utilization") is not None]
    ac_vals    = [r.get("answer_chars", 0) for r in records if r.get("answer_chars", 0) > 0]
    in_tok     = [r.get("input_tokens", 0) for r in records]
    out_tok    = [r.get("output_tokens", 0) for r in records]
    cost_vals  = [r.get("cost_usd", 0.0) for r in records]

    def _fmt(vals, fmt=".3f"):
        return f"{np.mean(vals):{fmt}}" if vals else "—"

    lines = [
        f"Cases          : {n}",
        f"Passed         : {n_pass}  ({n_pass/n*100:.0f}%)",
        f"Model(s)       : {', '.join(model_ids) or '—'}",
        f"",
        f"Accuracy",
        f"  binary       : {n_pass/n:.3f}",
        f"  avg check    : {np.mean(cs_vals):.3f}",
        f"  avg quality  : {np.mean(qs_vals):.3f}",
        f"",
        f"Tool F1        avg : {_fmt(f1_vals)}",
        f"Action F1      avg : {_fmt(af1_vals)}",
        f"Keyword cov.   avg : {_fmt(kw_vals)}",
        f"",
        f"Efficiency",
        f"  avg rounds util : {_fmt(ru_vals)}",
        f"  avg cost util   : {_fmt(cu_vals)}",
        f"  avg ms/round    : {_fmt(mpr_vals, '.0f')}",
        f"",
        f"Tokens (per case)",
        f"  input  avg   : {np.mean(in_tok):,.0f}",
        f"  output avg   : {np.mean(out_tok):,.0f}",
        f"  cost   avg   : ${np.mean(cost_vals):.4f}",
        f"  cost   total : ${sum(cost_vals):.4f}",
        f"",
        f"Answer length",
        f"  avg : {np.mean(ac_vals):,.0f} chars" if ac_vals else "  avg : —",
        f"  max : {max(ac_vals):,} chars" if ac_vals else "  max : —",
    ]
    ax.text(
        0.05, 0.96, "\n".join(lines),
        transform=ax.transAxes,
        fontsize=8.5, va="top", family="monospace",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#F5F5F5", edgecolor="#CCCCCC"),
    )
    ax.set_title("Summary", fontsize=10, fontweight="bold")


def _draw_error_taxonomy(ax, records: list[dict]) -> None:
    error_cats = [r.get("error_category") for r in records if not r.get("passed")]
    err_counter = Counter(c for c in error_cats if c)
    items = err_counter.most_common(12)
    if not items:
        ax.set_visible(False)
        return
    labels, values = zip(*items)
    y = range(len(labels))
    ax.barh(y, values, color=RED, alpha=0.85)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_title("Error taxonomy (failed cases)", fontsize=10, fontweight="bold")
    ax.set_xlabel("count", fontsize=8)
    for i, v in enumerate(values):
        ax.text(v + max(values) * 0.01, i, str(v), va="center", fontsize=7)
    _spines_off(ax)


def _draw_check_type_rates(ax, records: list[dict]) -> None:
    ct_rates = _build_check_type_rates(records)
    if not ct_rates:
        ax.set_visible(False)
        return
    ct_labels = list(ct_rates.keys())
    ct_vals = [ct_rates[k] for k in ct_labels]
    y = range(len(ct_labels))
    colors_ct = [GREEN if v >= 0.8 else ORANGE if v >= 0.5 else RED for v in ct_vals]
    ax.barh(y, ct_vals, color=colors_ct, alpha=0.85)
    ax.set_yticks(y)
    ax.set_yticklabels(ct_labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.axvline(1.0, color=GREY, lw=0.8, ls="--")
    ax.set_title("Pass rate by check type", fontsize=10, fontweight="bold")
    ax.set_xlabel("pass rate (0–1)", fontsize=8)
    for i, v in enumerate(ct_vals):
        ax.text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=7)
    _spines_off(ax)


def _draw_keyword_coverage(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    kw_raw = [r.get("keyword_coverage") for r in records]
    kw_vals = [v if v is not None else 0.0 for v in kw_raw]
    kw_defined = [v is not None for v in kw_raw]
    kw_colors = [GREEN if v == 1.0 else ORANGE if v >= 0.5 else RED for v in kw_vals]
    ax.bar(x, kw_vals, color=kw_colors, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_ylim(0, 1.1)
    ax.set_title("Keyword coverage per case", fontsize=10, fontweight="bold")
    ax.set_ylabel("fraction found", fontsize=8)
    for i, defined in enumerate(kw_defined):
        if not defined:
            ax.get_children()[i].set_alpha(0.2)
    _spines_off(ax)


def _draw_score_per_case(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    w = 0.4
    check_scores   = [r.get("check_score", 1.0) for r in records]
    quality_scores = [r.get("quality_check_score", 1.0) for r in records]
    ax.bar(x - w/2, check_scores,   width=w, label="check_score",         color=BLUE,   alpha=0.8)
    ax.bar(x + w/2, quality_scores, width=w, label="quality_check_score", color=PURPLE, alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_ylim(0, 1.1)
    ax.set_title("Check score vs quality check score per case", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    _spines_off(ax)


def _draw_tool_metrics_per_case(ax, records: list[dict]) -> None:
    """Grouped bars: tool_precision (blue), tool_recall (green), tool_f1 (orange) per case."""
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    w = 0.25

    prec_vals = [r.get("tool_precision") for r in records]
    rec_vals  = [r.get("tool_recall") for r in records]
    f1_vals   = [r.get("tool_f1") for r in records]

    if all(v is None for v in f1_vals):
        ax.set_visible(False)
        return

    def _safe(vals):
        return [v if v is not None else 0.0 for v in vals]

    bars_p = ax.bar(x - w, _safe(prec_vals), width=w, label="precision", color=BLUE,   alpha=0.8)
    bars_r = ax.bar(x,     _safe(rec_vals),  width=w, label="recall",    color=GREEN,  alpha=0.8)
    bars_f = ax.bar(x + w, _safe(f1_vals),   width=w, label="F1",        color=ORANGE, alpha=0.8)

    # Grey out bars where tool metric is None (no expected_tools defined)
    for i, v in enumerate(prec_vals):
        if v is None:
            bars_p[i].set_color(GREY)
            bars_r[i].set_color(GREY)
            bars_f[i].set_color(GREY)
            bars_p[i].set_alpha(0.4)
            bars_r[i].set_alpha(0.4)
            bars_f[i].set_alpha(0.4)

    valid_f1 = [v for v in f1_vals if v is not None]
    title_suffix = f"  avg F1={np.mean(valid_f1):.2f}" if valid_f1 else ""
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_ylim(0, 1.1)
    ax.set_title(f"Tool precision / recall / F1 per case{title_suffix}", fontsize=10, fontweight="bold")
    ax.legend(fontsize=7)
    _spines_off(ax)


def _draw_action_f1_per_case(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    af1_vals = [r.get("action_f1") for r in records]

    if all(v is None for v in af1_vals):
        ax.set_visible(False)
        return

    vals = [v if v is not None else 0.0 for v in af1_vals]
    colors = [
        (GREEN if v >= 0.8 else ORANGE if v >= 0.5 else RED) if af1_vals[i] is not None else GREY
        for i, v in enumerate(vals)
    ]
    ax.bar(x, vals, color=colors, alpha=0.85)
    valid = [v for v in af1_vals if v is not None]
    if valid:
        ax.axhline(np.mean(valid), color=BLUE, lw=1.2, ls="--",
                   label=f"avg {np.mean(valid):.2f}")
        ax.legend(fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_ylim(0, 1.1)
    ax.set_title("Action F1 per case (grey = no expected_actions)", fontsize=10, fontweight="bold")
    ax.set_ylabel("F1", fontsize=8)
    _spines_off(ax)


def _draw_rounds_utilization(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    ru_raw = [r.get("rounds_utilization") for r in records]
    ru_vals = [v if v is not None else 0.0 for v in ru_raw]
    ru_colors = [
        (RED if v > 1.0 else ORANGE if v > 0.8 else GREEN) if ru_raw[i] is not None else GREY
        for i, v in enumerate(ru_vals)
    ]
    ax.bar(x, ru_vals, color=ru_colors, alpha=0.85)
    ax.axhline(1.0, color=RED, lw=1.2, ls="--", label="limit (1.0)")
    ax.axhline(0.8, color=ORANGE, lw=0.8, ls=":", label="near-limit (0.8)")
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_title("Rounds utilization per case (grey = no max_rounds)", fontsize=10, fontweight="bold")
    ax.set_ylabel("rounds / max_rounds", fontsize=8)
    ax.legend(fontsize=8)
    _spines_off(ax)


def _draw_cost_utilization(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    cu_raw = [r.get("cost_utilization") for r in records]

    if all(v is None for v in cu_raw):
        ax.set_visible(False)
        return

    cu_vals = [v if v is not None else 0.0 for v in cu_raw]
    cu_colors = [
        (RED if v > 1.0 else ORANGE if v > 0.8 else GREEN) if cu_raw[i] is not None else GREY
        for i, v in enumerate(cu_vals)
    ]
    ax.bar(x, cu_vals, color=cu_colors, alpha=0.85)
    ax.axhline(1.0, color=RED, lw=1.2, ls="--", label="limit (1.0)")
    ax.axhline(0.8, color=ORANGE, lw=0.8, ls=":", label="near-limit (0.8)")
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_title("Cost utilization per case (grey = no max_cost_usd)", fontsize=10, fontweight="bold")
    ax.set_ylabel("cost / max_cost_usd", fontsize=8)
    ax.legend(fontsize=8)
    _spines_off(ax)


def _draw_ms_per_round(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    mpr_raw = [r.get("ms_per_round") for r in records]
    mpr_vals = [v if v is not None else float("nan") for v in mpr_raw]
    colors = [TEAL if not np.isnan(v) else GREY for v in mpr_vals]
    ax.bar(x, [0 if np.isnan(v) else v for v in mpr_vals], color=colors, alpha=0.85)
    valid = [v for v in mpr_vals if not np.isnan(v)]
    if valid:
        ax.axhline(np.mean(valid), color=RED, lw=1.2, ls="--",
                   label=f"avg {np.mean(valid):.0f}ms")
        ax.legend(fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_title("Latency per round (ms)", fontsize=10, fontweight="bold")
    ax.set_ylabel("ms / round", fontsize=8)
    _spines_off(ax)


def _draw_answer_chars(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    x = np.arange(n)
    ac_vals = [r.get("answer_chars", 0) for r in records]
    colors = [TEAL if v > 0 else GREY for v in ac_vals]
    ax.bar(x, ac_vals, color=colors, alpha=0.85)
    non_zero = [v for v in ac_vals if v > 0]
    if non_zero:
        ax.axhline(np.mean(non_zero), color=RED, lw=1.2, ls="--",
                   label=f"avg {np.mean(non_zero):,.0f}")
        ax.legend(fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(short_ids, rotation=40, ha="right", fontsize=6)
    ax.set_title("Answer length per case (chars)", fontsize=10, fontweight="bold")
    ax.set_ylabel("characters", fontsize=8)
    _spines_off(ax)


def _draw_tokens_vs_check_score(ax, records: list[dict]) -> None:
    difficulties = [(r.get("metadata") or {}).get("difficulty", "") or "unknown" for r in records]
    short_ids = _short_ids(records)
    in_tok  = [r.get("input_tokens", 0) for r in records]
    out_tok = [r.get("output_tokens", 0) for r in records]
    total_tokens = [i + o for i, o in zip(in_tok, out_tok)]
    check_scores = [r.get("check_score", 1.0) for r in records]
    for d in sorted(set(difficulties)):
        mask = [di == d for di in difficulties]
        ax.scatter(
            [t for t, m in zip(total_tokens, mask) if m],
            [cs for cs, m in zip(check_scores, mask) if m],
            color=DIFF_COLORS.get(d, GREY), alpha=0.8, s=60,
            edgecolors="white", label=d,
        )
    for i, (t, cs) in enumerate(zip(total_tokens, check_scores)):
        ax.annotate(_short(short_ids[i], 14), (t, cs),
                    fontsize=5, alpha=0.6, xytext=(3, 2), textcoords="offset points")
    ax.set_xlabel("total tokens", fontsize=8)
    ax.set_ylabel("check_score", fontsize=8)
    ax.set_title("Tokens vs check_score (by difficulty)", fontsize=10, fontweight="bold")
    ax.legend(fontsize=7, title="difficulty")
    _spines_off(ax)


def _draw_cost_vs_check_score(ax, records: list[dict]) -> None:
    categories = [(r.get("metadata") or {}).get("category", "") or "unknown" for r in records]
    short_ids = _short_ids(records)
    unique_cats = sorted(set(categories))
    cat_color = {c: CAT_PALETTE[i % len(CAT_PALETTE)] for i, c in enumerate(unique_cats)}
    cost_usd    = [r.get("cost_usd", 0.0) for r in records]
    check_scores = [r.get("check_score", 1.0) for r in records]
    for i, (c, cs, cat) in enumerate(zip(cost_usd, check_scores, categories)):
        ax.scatter(c, cs, color=cat_color[cat], alpha=0.8, s=60, edgecolors="white")
        ax.annotate(_short(short_ids[i], 14), (c, cs),
                    fontsize=5, alpha=0.6, xytext=(3, 2), textcoords="offset points")
    cat_patches = [mpatches.Patch(color=cat_color[c], label=c) for c in unique_cats]
    ax.legend(handles=cat_patches, fontsize=6, title="category")
    ax.set_xlabel("cost (USD)", fontsize=8)
    ax.set_ylabel("check_score", fontsize=8)
    ax.set_title("Cost vs check_score (by category)", fontsize=10, fontweight="bold")
    _spines_off(ax)


def _draw_category_accuracy(ax, records: list[dict]) -> None:
    groups = _aggregate_by_group(records, "category")
    cat_order = sorted(groups.keys())
    unique_cats = sorted(set(cat_order))
    cat_color = {c: CAT_PALETTE[i % len(CAT_PALETTE)] for i, c in enumerate(unique_cats)}
    pass_rates = [
        groups[c]["pass"] / (groups[c]["pass"] + groups[c]["fail"])
        for c in cat_order
    ]
    cs_means = [np.mean(groups[c]["cs"]) for c in cat_order]
    xc = np.arange(len(cat_order))
    ax.bar(xc, pass_rates, color=[cat_color[c] for c in cat_order], alpha=0.8, width=0.5)
    ax.plot(xc, cs_means, "o--", color=BLUE, lw=1.5, ms=6, label="avg check_score")
    ax.set_xticks(xc)
    ax.set_xticklabels(cat_order, fontsize=9)
    ax.set_ylim(0, 1.15)
    ax.set_title("Accuracy by category", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    for i, v in enumerate(pass_rates):
        ax.text(i, v + 0.03, f"{v:.0%}", ha="center", fontsize=8, fontweight="bold")
    _spines_off(ax)


def _is_multi_model(records: list[dict]) -> bool:
    """True when records span more than one distinct model_id."""
    return len({r.get("model_id", "") for r in records if r.get("model_id")}) > 1


def _draw_multi_model_accuracy(ax, records: list[dict]) -> None:
    """Grouped bar: binary accuracy + avg check_score per model."""
    model_ids = sorted({r.get("model_id", "unknown") for r in records})
    accs, css = [], []
    for mid in model_ids:
        group = [r for r in records if r.get("model_id") == mid]
        n = len(group)
        accs.append(sum(1 for r in group if r.get("passed")) / n if n else 0.0)
        css.append(float(np.mean([r.get("check_score", 1.0) for r in group])) if group else 0.0)

    x = np.arange(len(model_ids))
    w = 0.35
    bars_acc = ax.bar(x - w / 2, accs, width=w, color=GREEN, alpha=0.85, label="binary acc")
    bars_cs = ax.bar(x + w / 2, css, width=w, color=BLUE, alpha=0.85, label="avg check_score")
    ax.set_xticks(x)
    ax.set_xticklabels(
        [_short(mid.replace("vertex_ai/", ""), 22) for mid in model_ids],
        rotation=20, ha="right", fontsize=8,
    )
    ax.set_ylim(0, 1.15)
    ax.axhline(1.0, color=GREY, lw=0.8, ls="--")
    ax.set_title("Accuracy by model", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    for bar, val in [(b, v) for b, v in zip(bars_acc, accs)] + [(b, v) for b, v in zip(bars_cs, css)]:
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.02, f"{val:.2f}",
                ha="center", fontsize=7)
    _spines_off(ax)


def _draw_cross_run_trend(ax, paths: list[Path]) -> None:
    ax.set_title("Accuracy trend across runs", fontsize=10, fontweight="bold")
    if len(paths) > 1:
        run_stats = []
        for p in sorted(paths):
            recs = load_benchmark_jsonl([p])
            if recs:
                ts = recs[0].get("timestamp", p.stem)[:15]
                run_stats.append({
                    "ts": ts,
                    "acc": sum(1 for r in recs if r.get("passed")) / len(recs),
                    "cs": np.mean([r.get("check_score", 1.0) for r in recs]),
                })
        if run_stats:
            xs = range(len(run_stats))
            ax.plot(xs, [s["acc"] for s in run_stats], "o-", color=GREEN,
                    lw=2, ms=7, label="binary acc")
            ax.plot(xs, [s["cs"] for s in run_stats], "s--", color=BLUE,
                    lw=1.5, ms=5, label="check_score")
            ax.set_xticks(xs)
            ax.set_xticklabels([s["ts"] for s in run_stats],
                               rotation=25, ha="right", fontsize=7)
            ax.set_ylim(0, 1.1)
            ax.axhline(1.0, color=GREY, lw=0.8, ls="--")
            ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "Pass multiple files\nto show trend",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=9, color=GREY)
    _spines_off(ax)


def _draw_tools_heatmap(ax, records: list[dict]) -> None:
    short_ids = _short_ids(records)
    n = len(records)
    all_tools: set = set()
    case_tool_data = []
    for r in records:
        expected_t, actual_t, missing_t = set(), set(), set()
        for c in (r.get("checks") or []):
            if c.get("check") == "expected_tools":
                expected_t = set(c.get("expected") or [])
                actual_t   = set(c.get("actual") or [])
                missing_t  = set(c.get("missing") or [])
        all_tools |= expected_t | actual_t
        case_tool_data.append({"expected": expected_t, "actual": actual_t, "missing": missing_t})

    tool_list = sorted(all_tools)
    if not tool_list:
        ax.text(0.5, 0.5, "No expected_tools checks found",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=9, color=GREY)
        ax.set_title("Expected vs actual tools", fontsize=10, fontweight="bold")
        return

    heat_matrix = np.zeros((n, len(tool_list)))
    for i, d in enumerate(case_tool_data):
        for j, t in enumerate(tool_list):
            if t in d["missing"]:
                heat_matrix[i, j] = -1
            elif t in (d["expected"] & d["actual"]):
                heat_matrix[i, j] = 2
            elif t in d["actual"]:
                heat_matrix[i, j] = 1
    heat_cmap = matplotlib.colors.ListedColormap([RED, "#EEEEEE", ORANGE, GREEN])
    ax.imshow(heat_matrix, aspect="auto", cmap=heat_cmap,
              vmin=-1, vmax=2, interpolation="none")
    ax.set_xticks(range(len(tool_list)))
    ax.set_xticklabels(tool_list, rotation=40, ha="right", fontsize=7)
    ax.set_yticks(range(n))
    ax.set_yticklabels(short_ids, fontsize=6)
    legend_patches = [
        mpatches.Patch(color=GREEN,     label="expected + called"),
        mpatches.Patch(color=RED,       label="expected, not called"),
        mpatches.Patch(color=ORANGE,    label="extra call"),
        mpatches.Patch(color="#EEEEEE", label="not involved"),
    ]
    ax.legend(handles=legend_patches, fontsize=6,
              loc="upper right", bbox_to_anchor=(1.0, -0.15), ncol=2)
    ax.set_title("Expected vs actual tools", fontsize=10, fontweight="bold")


# ── figure builder ────────────────────────────────────────────────────────────

def _build_figure(records: list[dict], paths: list[Path]) -> plt.Figure:
    """Build the 6×3 benchmark dashboard figure."""
    n = len(records)
    n_pass = sum(1 for r in records if r.get("passed"))
    avg_cs = np.mean([r.get("check_score", 1.0) for r in records])

    model_ids = sorted({r.get("model_id", "") for r in records if r.get("model_id")})
    model_label = (
        f"models: {', '.join(model_ids)}"
        if len(model_ids) > 1
        else (model_ids[0] if model_ids else "")
    )
    fig = plt.figure(figsize=(22, 36))
    fig.suptitle(
        f"GeoAgentBench — Benchmark Dashboard  ({n} cases, {n_pass}/{n} passed, "
        f"avg check_score={avg_cs:.2f})  [{model_label}]",
        fontsize=14, fontweight="bold", y=0.988,
    )
    gs = gridspec.GridSpec(
        6, 3, figure=fig,
        hspace=0.55, wspace=0.38,
        left=0.07, right=0.97,
        top=0.975, bottom=0.02,
    )

    # Row 0 — accuracy overview
    _draw_accuracy_overview(fig.add_subplot(gs[0, 0]), records)
    _draw_difficulty_accuracy(fig.add_subplot(gs[0, 1]), records)
    _draw_summary_box(fig.add_subplot(gs[0, 2]), records)

    # Row 1 — failure breakdown + check quality
    _draw_error_taxonomy(fig.add_subplot(gs[1, 0]), records)
    _draw_check_type_rates(fig.add_subplot(gs[1, 1]), records)
    _draw_keyword_coverage(fig.add_subplot(gs[1, 2]), records)

    # Row 2 — partial credit + tool metrics
    _draw_score_per_case(fig.add_subplot(gs[2, 0]), records)
    _draw_tool_metrics_per_case(fig.add_subplot(gs[2, 1]), records)
    _draw_action_f1_per_case(fig.add_subplot(gs[2, 2]), records)

    # Row 3 — budget utilization + latency
    _draw_rounds_utilization(fig.add_subplot(gs[3, 0]), records)
    _draw_cost_utilization(fig.add_subplot(gs[3, 1]), records)
    _draw_ms_per_round(fig.add_subplot(gs[3, 2]), records)

    # Row 4 — verbosity + token/cost efficiency scatters
    _draw_answer_chars(fig.add_subplot(gs[4, 0]), records)
    _draw_tokens_vs_check_score(fig.add_subplot(gs[4, 1]), records)
    _draw_cost_vs_check_score(fig.add_subplot(gs[4, 2]), records)

    # Row 5 — aggregate analysis
    _draw_category_accuracy(fig.add_subplot(gs[5, 0]), records)
    if _is_multi_model(records):
        _draw_multi_model_accuracy(fig.add_subplot(gs[5, 1]), records)
    else:
        _draw_cross_run_trend(fig.add_subplot(gs[5, 1]), paths)
    _draw_tools_heatmap(fig.add_subplot(gs[5, 2]), records)

    return fig


# ── public API ────────────────────────────────────────────────────────────────

def plot_benchmark(records: list[dict], output_path: str) -> None:
    """Save benchmark dashboard PNG to output_path.

    Called from runner.py after experiments complete so the PNG is
    included in the gsutil rsync upload to GCS.
    """
    if not records:
        return
    fig = _build_figure(records, paths=[])
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="Benchmark JSONL files (default: results/*.jsonl)")
    parser.add_argument("--out", default="", help="Save figure to this path instead of showing")
    args = parser.parse_args()

    if args.files:
        paths = [Path(p) for p in args.files]
    else:
        root = Path(__file__).parent.parent
        paths = sorted((root / "results").glob("*.jsonl"))

    if not paths:
        print("No benchmark JSONL files found. Run geoagentbench first or pass file paths.", file=sys.stderr)
        sys.exit(1)

    records = load_benchmark_jsonl(paths)
    if not records:
        print("No benchmark records found (looking for lines with case_id but no event field).", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(records)} benchmark results from {len(paths)} file(s).")

    if args.out:
        plot_benchmark(records, args.out)
        print(f"Saved to {args.out}")
    else:
        fig = _build_figure(records, paths)
        plt.show()
        plt.close(fig)


if __name__ == "__main__":
    main()
