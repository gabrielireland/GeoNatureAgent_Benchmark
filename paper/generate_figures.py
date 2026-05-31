"""Generate all paper figures for GeoNatureAgent Benchmark v5.

Numbers are loaded from `paper/final_results/leaderboard.csv` and
`paper/final_results/per_category.csv`, which are produced by
`scripts/compile_final_results.py`. To refresh after a new model run:

    python scripts/compile_final_results.py
    python paper/generate_figures.py
"""

import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path
from adjustText import adjust_text

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
RESULTS = Path(__file__).parent / "final_results"


def _load_leaderboard():
    with (RESULTS / "leaderboard.csv").open() as f:
        return list(csv.DictReader(f))


def _load_per_category():
    with (RESULTS / "per_category.csv").open() as f:
        return {row["model"]: row for row in csv.DictReader(f)}

# ── Shared style — academic / SIGSPATIAL register ────────────────────────
# Hybrid approach: austere grayscale for single-series bars/diagrams,
# ColorBrewer Dark2 (7-class qualitative, print-safe) where categorical
# model identity is shown, viridis for the sequential heatmap.
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman", "STIX Two Text", "DejaVu Serif", "Times New Roman"],
    "mathtext.fontset": "stix",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.8,
    "axes.labelcolor": "#222222",
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "legend.fontsize": 9,
    "legend.frameon": False,
    "figure.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
})

# ── ColorBrewer Dark2 — 8-class qualitative, designed for print ──────────
DARK2 = [
    "#1b9e77",  # teal-green
    "#d95f02",  # orange
    "#7570b3",  # slate purple
    "#e7298a",  # magenta
    "#66a61e",  # olive green
    "#e6ab02",  # ochre
    "#a6761d",  # brown
    "#666666",  # neutral gray (8th class)
]

# ── Grayscale tones ───────────────────────────────────────────────────────
GRAY_BAR = "#4a4a4a"        # primary single-series bar fill
GRAY_BAR_ALT = "#9a9a9a"    # secondary paired-bar fill
GRAY_LINE = "#333333"       # axis / annotation
GRAY_AXIS = "#888888"       # reference lines, light annotations

# Diagram fill tones — soft pastel palette (print-safe, academic).
# Each hue marks a distinct semantic role; dark edge is shared across all.
DIAG_INPUT    = "#dbe8f4"   # soft blue   — origin / source data
DIAG_PROCESS  = "#e8def0"   # soft lavender — computation
DIAG_DATA     = "#fce9c6"   # soft peach  — storage / aggregator
DIAG_OUTPUT   = "#dbeed1"   # soft green  — result / answer
DIAG_DECISION = "#fff2cc"   # soft yellow — branching decision

# Legacy aliases — preserved so existing figure code still resolves.
C_DARK = GRAY_LINE
C_GRAY = GRAY_AXIS
C_BLUE = GRAY_BAR
C_TEAL = GRAY_BAR_ALT
C_GREEN = DARK2[0]
C_ORANGE = DARK2[1]
C_RED = DARK2[3]
C_PURPLE = DARK2[2]
C_PINK = DARK2[3]
C_INDIGO = DARK2[2]

# ── v5 Data — loaded from paper/final_results/*.csv ──────────────────────
# Single source of truth: scripts/compile_final_results.py produced these CSVs
# from raw GCS results.jsonl files. No hand-edited numbers below this line.
_LB = _load_leaderboard()
_CAT = _load_per_category()

models = [r["model"] for r in _LB]                              # sorted by accuracy desc
accuracy = [float(r["accuracy_mean"]) * 100 for r in _LB]       # percent
accuracy_std = [float(r["accuracy_std"]) * 100 for r in _LB]    # variance bars
check_score = [float(r["check_score_mean"]) for r in _LB]
kw_coverage = [float(r["keyword_coverage_mean"]) for r in _LB]
cost_total = [float(r["cost_per_seed_mean"]) for r in _LB]      # one-seed equivalent
cost_per_case = [float(r["cost_per_case"]) for r in _LB]
tokens_k = [float(r["tokens_per_seed_mean"]) / 1000 for r in _LB]

# Per-model categorical colors — ColorBrewer Dark2, applied in leaderboard order
# (fig2 cost-accuracy, fig7 tokens-accuracy use these).
_PALETTE = DARK2[:7]
model_colors = _PALETTE[: len(models)]

# All models go into every figure; no historical exclusion is applied.
completed_models = models[:]
completed_accuracy = accuracy[:]

categories_all = [
    "tool_selection", "cross_indicator", "interpretation", "deep_dive",
    "error_handling", "habitat_analysis", "language", "municipality",
    "memory", "spatial_reasoning", "temporal_change", "error_recovery",
    "multi_municipality_ranking", "threshold", "comparison", "ranking",
    "single_analysis", "province_aggregation",
]
cat_labels = [
    "Tool selection", "Cross-indicator", "Interpretation", "Deep dive",
    "Error handling", "Habitat analysis", "Language", "Municipality",
    "Memory", "Spatial reasoning", "Temporal change", "Error recovery",
    "Multi-muni ranking", "Threshold", "Comparison", "Ranking",
    "Single analysis", "Province aggregation",
]
cat_counts = [21, 8, 7, 6, 6, 7, 6, 4, 6, 4, 1, 3, 3, 3, 2, 2, 2, 2]

# Per-model category accuracy (%) — restricted to completed_models for heatmap
cat_data = {
    m: [round(float(_CAT[m][cat]) * 100) for cat in categories_all]
    for m in completed_models if m in _CAT
}

cat_avg = {
    cat: sum(cat_data[m][j] for m in cat_data) / len(cat_data)
    for j, cat in enumerate(categories_all)
}


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 1: Leaderboard — Accuracy bar chart (horizontal)
# ═══════════════════════════════════════════════════════════════════════════
def fig1_leaderboard():
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(models))
    ax.barh(y, accuracy, color=model_colors, edgecolor="white", linewidth=0.5, height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(models)
    ax.set_xlabel("Accuracy (%)", fontsize=11, fontweight="bold")
    ax.tick_params(axis='both', labelsize=10)
    ax.set_xlim(0, 79)
    ax.set_title(f"GeoNatureAgent Benchmark v5 — Model Accuracy (93 tasks, {len(models)} models)")
    ax.invert_yaxis()
    # Variance bars (per-seed standard deviation) where available.
    for i, (v, sd) in enumerate(zip(accuracy, accuracy_std)):
        if sd > 0:
            ax.errorbar(v, i, xerr=sd, fmt="none", ecolor=C_DARK, capsize=3,
                        elinewidth=0.8, alpha=0.8)
    for i, (v, c, sd) in enumerate(zip(accuracy, cost_total, accuracy_std)):
        cost_str = f"${c:.2f}" if c > 0 else "---"
        label = f"{v:.1f}% ±{sd:.1f}  ({cost_str})" if sd > 0 else f"{v:.1f}%  ({cost_str})"
        ax.text(v + sd + 0.5, i, label, va="center", fontsize=9, color=C_DARK)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.axvline(50, color=C_GRAY, linestyle="--", linewidth=0.7, alpha=0.5)
    fig.savefig(OUT / "fig1_leaderboard.pdf")
    fig.savefig(OUT / "fig1_leaderboard.png")
    plt.close(fig)
    print("  fig1_leaderboard")


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 2: Cost-Accuracy scatter (Pareto frontier)
# ═══════════════════════════════════════════════════════════════════════════
def fig2_cost_accuracy():
    plot_models = models[:]
    plot_acc = accuracy[:]
    plot_cost = cost_total[:]
    plot_tokens = tokens_k[:]
    plot_colors = model_colors[:]

    fig, ax = plt.subplots(figsize=(5.5, 4))
    texts = []
    for i, m in enumerate(plot_models):
        size = max(plot_tokens[i] * 0.12, 30)
        ax.scatter(plot_cost[i], plot_acc[i], s=size, c=plot_colors[i],
                   alpha=0.85, edgecolor=C_DARK, linewidth=0.5, zorder=3)
        txt = ax.text(
            plot_cost[i]-1,
            plot_acc[i]-6.5,
            m,
            fontsize=8,
            fontweight="bold"
            )
        texts.append(txt)

    adjust_text(texts, ax=ax,
            expand_text=(4.0, 4.0),
            expand_points=(4.0, 4.0),
            force_text=(2.0, 2.0),
            force_points=(2.0, 2.0))

    # Pareto frontier — computed from the data rather than hard-coded.
    pts = sorted(zip(plot_cost, plot_acc))
    pareto = []
    best_acc = -1.0
    for x, y in pts:
        if y > best_acc:
            pareto.append((x, y))
            best_acc = y
    if pareto:
        px, py = zip(*pareto)
        ax.plot(px, py, "--", color=C_DARK, linewidth=0.8, alpha=0.4, zorder=1)
        # Place the label near the upper-right end of the frontier.
        ax.annotate("Pareto frontier",
                    xy=(px[-1] * 0.6, py[-1] - 4),
                    xytext=(-35, 9), textcoords="offset points",
                    fontsize=9, fontweight="bold",
                    color=C_GRAY, style="italic")

    x_max = max(plot_cost) * 1.25 + 0.3
    y_max = max(plot_acc) * 1.15 + 3
    ax.set_xlabel("Cost per Seed Run (USD, 93 cases)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Accuracy (%)", fontsize=11, fontweight="bold")
    ax.tick_params(axis='both', labelsize=10)
    ax.set_title("Cost-Accuracy Trade-off\n(bubble size = total tokens)")
    ax.set_xlim(-0.3, x_max)
    ax.set_ylim(-2, y_max)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.savefig(OUT / "fig2_cost_accuracy.pdf")
    fig.savefig(OUT / "fig2_cost_accuracy.png")
    plt.close(fig)
    print("  fig2_cost_accuracy")



# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 3: Binary accuracy vs partial-credit check score
# ═══════════════════════════════════════════════════════════════════════════
def fig3_binary_vs_partial():
    fig, ax = plt.subplots(figsize=(7, 3.5))
    x = np.arange(len(models))
    w = 0.40
    # Per-model color identity stays consistent with fig1/fig2/fig7.
    # Binary bars at full saturation; partial-credit bars at alpha=0.55 for contrast.
    partial_scores = np.array(check_score) * 100

    # Binary accuracy bars
    bars1 = ax.bar(
        x - w / 2,
        accuracy,
        width=w,
        label="Binary Accuracy (%)",
        color=model_colors,
        edgecolor="white",
        linewidth=0.4,
    )

    # Partial-credit bars
    bars2 = ax.bar(
        x + w / 2,
        partial_scores,
        width=w,
        label="Partial Credit (%)",
        color=model_colors,
        edgecolor="white",
        linewidth=0.4,
        alpha=0.55,
    )

    # --- Add values inside bars ---
    for bar in bars1:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h - 3,
            f"{h:.1f}",
            ha="center",
            va="top",
            fontsize=8,
            color="white",
            fontweight="bold",
        )

    for bar in bars2:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h - 3,
            f"{h:.1f}",
            ha="center",
            va="top",
            fontsize=8,
            color="black",
        )
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=45, ha="right", fontsize=10)
    ax.set_ylabel("Score (%)", fontsize=11, fontweight="bold")
    ax.tick_params(axis='both', labelsize=10)
    ax.set_title("Binary Accuracy vs Partial Credit (93 tasks)")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_ylim(0, 105)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.savefig(OUT / "fig3_binary_vs_partial.pdf")
    fig.savefig(OUT / "fig3_binary_vs_partial.png")
    plt.close(fig)
    print("  fig3_binary_vs_partial")


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 4: Category accuracy heatmap (6 completed models x 18 categories)
# ═══════════════════════════════════════════════════════════════════════════
def fig4_category_heatmap():
    model_names = list(cat_data.keys())
    data = np.array([cat_data[m] for m in model_names])

    fig, ax = plt.subplots(figsize=(10, 4))
    im = ax.imshow(data, cmap="viridis", aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(np.arange(len(cat_labels)))
    ax.set_xticklabels(cat_labels, rotation=50, ha="right", fontsize=11)
    ax.set_yticks(np.arange(len(model_names)))
    ax.set_yticklabels(model_names, fontsize=11)
    for i in range(len(model_names)):
        for j in range(len(cat_labels)):
            v = data[i, j]
            # viridis: dark (purple/blue) at low values, bright (yellow) at high.
            color = "white" if v < 55 else "#222222"
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=11, fontweight='bold', color=color)
    ax.set_title(f"Accuracy by Category (%) — 18 categories, {len(model_names)} models")
    fig.colorbar(im, ax=ax, label="Accuracy %", shrink=0.8)
    fig.savefig(OUT / "fig4_category_heatmap.pdf")
    fig.savefig(OUT / "fig4_category_heatmap.png")
    plt.close(fig)
    print("  fig4_category_heatmap")


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 5: Universally hard categories (avg across 6 completed models)
# ═══════════════════════════════════════════════════════════════════════════
def fig5_hard_cases():
    # Sort categories by average accuracy
    sorted_cats = sorted(cat_avg.items(), key=lambda x: x[1])
    labels = [cat_labels[categories_all.index(c)] + f" (n={cat_counts[categories_all.index(c)]})"
              for c, _ in sorted_cats]
    rates = [v for _, v in sorted_cats]

    fig, ax = plt.subplots(figsize=(6.5, 5))
    # Soft amber accent — categorical-difficulty axis, not model identity.
    ax.barh(labels, rates, color="#d97706", height=0.65, edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Avg Accuracy (%)", fontsize=11, fontweight='bold')
    ax.set_xlim(0, 85)
    ax.tick_params(axis='both', labelsize=10)
    ax.set_title(f"Category Difficulty (avg across {len(cat_data)} models)")
    ax.invert_yaxis()
    for i, v in enumerate(rates):
        ax.text(v + 0.8, i, f"{v:.0f}%", va="center", fontsize=10, fontweight='bold')
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.savefig(OUT / "fig5_hard_cases.pdf")
    fig.savefig(OUT / "fig5_hard_cases.png")
    plt.close(fig)
    print("  fig5_hard_cases")


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 6: Agent architecture diagram
# ═══════════════════════════════════════════════════════════════════════════
def fig6_architecture():
    fig, ax = plt.subplots(figsize=(8.5, 6.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.set_aspect("equal")
    ax.axis("off")

    PAD = 0.1  # FancyBboxPatch round-pad; arrows must compensate to land on visible edges.
    boxes = [
        (0.5, 5.5, 2.0, 1.0, "User Query\n(NL + history)", DIAG_INPUT),
        (3.6, 5.5, 2.8, 1.0, "LLM Agent\n(ReAct loop)", DIAG_PROCESS),
        (3.6, 3.0, 2.8, 1.0, "Tool Router\n(16 tools)", DIAG_PROCESS),
        (7.5, 5.5, 2.0, 1.0, "Response\n(NL + data)", DIAG_OUTPUT),
        (7.5, 3.0, 2.0, 1.0, "Geospatial\nAPI (COGs)", DIAG_DATA),
        (3.6, 0.5, 2.8, 1.0, "Eval Harness\n(scoring)", DIAG_DECISION),
    ]
    for x, y, w, h, text, color in boxes:
        rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad={PAD}",
                                        facecolor=color, edgecolor=C_DARK, linewidth=1.2)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=13, fontweight="bold", color=C_DARK)

    # Arrows land on visible box edges: original edge ± PAD.
    arrows = [
        (2.5 + PAD, 6.0, 1.1 - 2 * PAD,  0),         # User → LLM
        (6.4 + PAD, 6.0, 1.1 - 2 * PAD,  0),         # LLM → Response
        (5.0,       5.5 - PAD, 0, -(1.5 - 2 * PAD)), # LLM ↓ Tool Router
        (5.0,       4.0 + PAD, 0,  (1.5 - 2 * PAD)), # Tool Router ↑ LLM
        (6.4 + PAD, 3.5, 1.1 - 2 * PAD,  0),         # Tool Router → Geo API
        (7.5 - PAD, 3.5, -(1.1 - 2 * PAD), 0),       # Geo API → Tool Router
        (5.0,       3.0 - PAD, 0, -(1.5 - 2 * PAD)), # Tool Router → Eval Harness
    ]
    for x, y, dx, dy in arrows:
        ax.annotate("", xy=(x + dx, y + dy), xytext=(x, y),
                    arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.2))

    ax.text(3.05, 6.2, "query", fontsize=12, color=C_GRAY, ha="center")
    ax.text(6.95, 6.2, "answer", fontsize=11, color=C_GRAY, ha="center")
    ax.text(4.6, 4.75, "tool calls", fontsize=12, color=C_GRAY, rotation=90, va="center")
    ax.text(5.1, 4.75, "results", fontsize=12, color=C_GRAY, rotation=90, va="center")
    ax.text(6.95, 3.7, "API", fontsize=12, color=C_GRAY, ha="center")
    ax.text(4.6, 2.2, "log", fontsize=12, color=C_GRAY, rotation=90, va="center")

    ax.set_title("GeoNatureAgent Benchmark — System Architecture", fontsize=13, fontweight="bold", pad=10)
    fig.savefig(OUT / "fig6_architecture.pdf")
    fig.savefig(OUT / "fig6_architecture.png")
    plt.close(fig)
    print("  fig6_architecture")


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 7: Token usage vs accuracy
# ═══════════════════════════════════════════════════════════════════════════
def fig7_tokens_vs_accuracy():
    plot_models = models[:]
    plot_acc = accuracy[:]
    plot_tokens = tokens_k[:]
    plot_colors = model_colors[:]

    fig, ax = plt.subplots(figsize=(8, 5))
    texts = []
    for i, m in enumerate(plot_models):
        ax.scatter(plot_tokens[i], plot_acc[i], s=80, c=plot_colors[i],
                   edgecolor=C_DARK, linewidth=0.5, zorder=3)
        txt = ax.text(
            plot_tokens[i]-90,
            plot_acc[i]-3,
            m,
            fontsize=9,
            fontweight="bold"
            )
        texts.append(txt)

    adjust_text(texts, ax=ax,
                expand_text=(4.0, 4.0),
                expand_points=(4.0, 4.0),
                force_text=(2.0, 2.0),
                force_points=(2.0, 2.0))
    ax.set_xlabel("Total Tokens (K)", fontsize=11, fontweight='bold')
    ax.set_ylabel("Accuracy (%)", fontsize=11, fontweight='bold')
    ax.set_ylim(0, 65)
    ax.tick_params(axis='both', labelsize=10)
    ax.set_title("Token Usage vs Accuracy (93 tasks)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.savefig(OUT / "fig7_tokens_accuracy.pdf")
    fig.savefig(OUT / "fig7_tokens_accuracy.png")
    plt.close(fig)
    print("  fig7_tokens_accuracy")


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 8: Scoring pipeline diagram
# ═══════════════════════════════════════════════════════════════════════════
def fig8_scoring_pipeline():
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.8)
    ax.set_aspect("equal")
    ax.axis("off")

    PAD = 0.08  # FancyBboxPatch round-pad; arrows must compensate to land on visible edges.

    def _box(x, y, w, h, text, color, fs=10):
        rect = mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle=f"round,pad={PAD}",
            facecolor=color, edgecolor=C_DARK, linewidth=1.0,
        )
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, fontweight="bold", color=C_DARK)

    def _arrow(x1, y1, x2, y2, label="", label_offset=(0, 0)):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.0))
        if label:
            mx = (x1 + x2) / 2 + label_offset[0]
            my = (y1 + y2) / 2 + label_offset[1]
            ax.text(mx, my, label, fontsize=10, color=C_DARK,
                    ha="center", va="center", fontweight="bold")

    # ── Row 1: Inputs ──
    # Task box:     x=0.8..2.8,  y=4.8..5.5 (visible y=4.72..5.58)
    # Agent Output: x=3.3..5.8,  y=4.8..5.5 (visible y=4.72..5.58)
    _box(0.5, 4.8, 2.3, 0.7, "Task\n(benchmark_v5.json)", DIAG_INPUT)
    _box(3.3, 4.8, 2.5, 0.7, "Agent Output\n(answer, tools, actions)", DIAG_PROCESS)

    # ── Row 2: Scoring checks + parallel Partial-Credit output (same y level) ──
    # 8 Checks:       x=0.5..6.1, y=3.2..4.0  (visible top y=4.08)
    # Partial Credit: x=6.7..9.7, y=3.1..4.1  (visible left edge x=6.62)
    _box(0.5, 3.2, 5.0, 0.8,
         "8 Scoring Checks (each produces pass / fail)",
         DIAG_DATA, fs=11)
    _box(6.0, 3.05, 3.8, 1.1,
         "Partial Credit\n(always computed)\n"
         "check_score · tool_f1 · keyword_coverage",
         DIAG_INPUT, fs=9)

    # Inputs → 8 Checks: arrows land on the visible top edge of the checks box.
    _arrow(1.65, 4.8 - PAD, 2.1, 4.0 + PAD)
    _arrow(4.55, 4.8 - PAD, 4.1, 4.0 + PAD)

    # 8 Checks → Partial Credit: horizontal arrow between visible edges.
    _arrow(5.5 + PAD, 3.6, 6.0 - PAD, 3.6)

    # ── Row 3: Decision diamond ──
    diamond_x, diamond_y = 3.3, 1.95
    dw, dh = 0.9, 0.45
    diamond = plt.Polygon([
        (diamond_x, diamond_y + dh),
        (diamond_x + dw, diamond_y),
        (diamond_x, diamond_y - dh),
        (diamond_x - dw, diamond_y),
    ], closed=True, facecolor=DIAG_DECISION, edgecolor=C_DARK, linewidth=1.0)
    ax.add_patch(diamond)
    ax.text(diamond_x, diamond_y, "ALL\npass?", fontsize=10, ha="center",
            va="center", fontweight="bold", color=C_DARK)

    # 8 Checks bottom-center → diamond top vertex.
    _arrow(diamond_x, 3.2 - PAD, diamond_x, diamond_y + dh)

    # ── Row 4: Binary outcomes — PASS / FAIL ──
    # PASS: x=0.5..2.0, y=0.4..1.0 (visible top y=1.08)
    # FAIL: x=4.6..6.1, y=0.4..1.0 (visible top y=1.08)
    _box(0.5, 0.4, 1.5, 0.6, "PASS\nbinary = 1", DIAG_OUTPUT)
    _box(4.6, 0.4, 1.5, 0.6, "FAIL\nerror_category", DIAG_OUTPUT)

    # Diamond → PASS / FAIL: tips land on each visible top edge.
    _arrow(diamond_x - dw, diamond_y, 1.25, 1.0 + PAD,
           "yes", label_offset=(-0.35, 0.2))
    _arrow(diamond_x + dw, diamond_y, 5.35, 1.0 + PAD,
           "no",  label_offset=(0.35, 0.2))

    ax.set_title("Scoring Pipeline — Per-Case Evaluation", fontsize=11,
                 fontweight="bold", pad=10)
    fig.savefig(OUT / "fig8_scoring_pipeline.pdf")
    fig.savefig(OUT / "fig8_scoring_pipeline.png")
    plt.close(fig)
    print("  fig8_scoring_pipeline")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating paper figures (v5 data)...")
    fig1_leaderboard()
    fig2_cost_accuracy()
    fig3_binary_vs_partial()
    fig4_category_heatmap()
    fig5_hard_cases()
    fig6_architecture()
    fig7_tokens_vs_accuracy()
    fig8_scoring_pipeline()
    print(f"Done. Figures saved to {OUT}/")
