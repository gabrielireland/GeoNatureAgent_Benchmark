"""Generate all paper figures for GeoNatureAgent Benchmark v5 (93 tasks, 8 models)."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)

# ── Shared style ──────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.1,
})

# Color palette
C_GREEN = "#2ecc71"
C_ORANGE = "#f39c12"
C_RED = "#e74c3c"
C_BLUE = "#3498db"
C_PURPLE = "#9b59b6"
C_TEAL = "#1abc9c"
C_DARK = "#2c3e50"
C_GRAY = "#95a5a6"
C_PINK = "#e91e63"
C_INDIGO = "#3f51b5"

# ── v5 Data (93 tasks, 8 models) ─────────────────────────────────────────
# Sorted by accuracy (descending) for leaderboard
models = [
    "GLM-5",
    "DeepSeek V3.2",
    "Claude Sonnet 4",
    "Qwen3-235B",
    "GPT-OSS-120B",
    "Gemini 2.5 Pro",
    "Llama 4 Scout",
    "Llama 4 Maverick",
]
accuracy = [58.1, 52.7, 58.1, 47.3, 39.8, 39.8, 5.4, 0.0]
check_score = [0.864, 0.871, 0.870, 0.825, 0.780, 0.787, 0.511, 0.460]
kw_coverage = [0.772, 0.834, 0.801, 0.772, 0.636, 0.689, 0.127, 0.000]
cost_total = [2.54, 0.79, 8.13, 0.50, 4.77, 2.99, 0.04, 0.00]
cost_per_case = [0.027, 0.008, 0.087, 0.005, 0.051, 0.032, 0.000, 0.000]
tokens_k = [2242, 2732, 2502, 1596, 1260, 1442, 252, 0]

# Model colors (consistent across all figures)
model_colors = [C_PURPLE, C_GREEN, C_INDIGO, C_TEAL, C_BLUE, C_ORANGE, C_RED, C_PINK]

# 6 completed models (excluding Maverick 0% infra failure and Scout 5.4%)
completed_models = models[:6]
completed_accuracy = accuracy[:6]

# Category data — all 18 categories, 6 completed models (excl Scout/Maverick)
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

# Per-model category accuracy (%) — 6 completed models
cat_data = {
    "GLM-5":          [67, 100, 43, 33, 67, 14, 50, 50, 83, 75, 100, 0, 67, 67, 0, 100, 50, 50],
    "DeepSeek V3.2":  [48, 100, 43, 33, 50, 14, 67, 75, 83, 75, 100, 0, 67, 67, 0, 50, 0, 50],
    "Claude Sonnet 4":[52, 100, 29, 50, 33, 86, 50, 100, 83, 50, 100, 0, 33, 100, 0, 100, 50, 0],
    "Qwen3-235B":     [29, 38, 29, 33, 100, 71, 50, 75, 67, 50, 100, 33, 33, 67, 0, 50, 100, 0],
    "GPT-OSS-120B":   [33, 62, 29, 0, 67, 43, 50, 75, 67, 0, 0, 33, 0, 67, 0, 50, 50, 50],
    "Gemini 2.5 Pro": [38, 50, 14, 33, 67, 57, 50, 50, 67, 25, 100, 0, 0, 33, 0, 0, 50, 50],
}

# Hard categories — average accuracy across 6 completed models
cat_avg = {}
for j, cat in enumerate(categories_all):
    vals = [cat_data[m][j] for m in cat_data]
    cat_avg[cat] = sum(vals) / len(vals)


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 1: Leaderboard — Accuracy bar chart (horizontal)
# ═══════════════════════════════════════════════════════════════════════════
def fig1_leaderboard():
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    y = np.arange(len(models))
    colors = [C_GREEN if a >= 40 else C_ORANGE if a >= 25 else C_RED for a in accuracy]
    ax.barh(y, accuracy, color=colors, edgecolor="white", linewidth=0.5, height=0.65)
    ax.set_yticks(y)
    ax.set_yticklabels(models)
    ax.set_xlabel("Accuracy (%)")
    ax.set_xlim(0, 70)
    ax.set_title("GeoNatureAgent Benchmark v5 — Model Accuracy (93 tasks, 8 models)")
    ax.invert_yaxis()
    for i, (v, c) in enumerate(zip(accuracy, cost_total)):
        cost_str = f"${c:.2f}" if c > 0 else "---"
        ax.text(v + 0.5, i, f"{v:.1f}%  ({cost_str})", va="center", fontsize=8, color=C_DARK)
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
    # Exclude Maverick (0 cost, 0 accuracy — infra failure)
    plot_models = models[:7]
    plot_acc = accuracy[:7]
    plot_cost = cost_total[:7]
    plot_tokens = tokens_k[:7]
    plot_colors = model_colors[:7]

    fig, ax = plt.subplots(figsize=(5.5, 4))
    for i, m in enumerate(plot_models):
        size = max(plot_tokens[i] * 0.12, 30)
        ax.scatter(plot_cost[i], plot_acc[i], s=size, c=plot_colors[i],
                   alpha=0.85, edgecolor=C_DARK, linewidth=0.5, zorder=3)
        # Smart label placement
        if m == "Claude Sonnet 4":
            xytext = (-8, -12)
            ha = "right"
        elif m == "Qwen3-235B":
            xytext = (5, -10)
            ha = "left"
        elif m == "Llama 4 Scout":
            xytext = (5, 5)
            ha = "left"
        else:
            xytext = (5, 5)
            ha = "left"
        ax.annotate(m, (plot_cost[i], plot_acc[i]),
                    textcoords="offset points", xytext=xytext,
                    fontsize=7.5, ha=ha, color=C_DARK)

    # Pareto frontier: Qwen3 → DeepSeek → GLM-5
    pareto_x = [0.50, 0.79, 2.54]
    pareto_y = [47.3, 52.7, 58.1]
    ax.plot(pareto_x, pareto_y, "--", color=C_DARK, linewidth=0.8, alpha=0.4, zorder=1)
    ax.annotate("Pareto frontier", xy=(1.2, 56), fontsize=7, color=C_GRAY, style="italic")

    ax.set_xlabel("Total Cost (USD)")
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Cost-Accuracy Trade-off\n(bubble size = total tokens)")
    ax.set_xlim(-0.3, 9.0)
    ax.set_ylim(-2, 68)
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
    w = 0.35
    ax.bar(x - w / 2, accuracy, w, label="Binary Accuracy (%)", color=C_BLUE, alpha=0.85)
    ax.bar(x + w / 2, [s * 100 for s in check_score], w,
           label="Avg Check Score (%)", color=C_TEAL, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Score (%)")
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
    im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(np.arange(len(cat_labels)))
    ax.set_xticklabels(cat_labels, rotation=50, ha="right", fontsize=7.5)
    ax.set_yticks(np.arange(len(model_names)))
    ax.set_yticklabels(model_names, fontsize=9)
    for i in range(len(model_names)):
        for j in range(len(cat_labels)):
            v = data[i, j]
            color = "white" if v < 25 or v > 80 else "black"
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7, color=color)
    ax.set_title("Accuracy by Category (%) — 18 categories, 6 completed models")
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
    labels = [cat_labels[categories_all.index(c)] + f"\n(n={cat_counts[categories_all.index(c)]})"
              for c, _ in sorted_cats]
    rates = [v for _, v in sorted_cats]

    fig, ax = plt.subplots(figsize=(6.5, 5))
    colors = [C_RED if r < 10 else C_ORANGE if r < 30 else C_GREEN for r in rates]
    ax.barh(labels, rates, color=colors, height=0.6)
    ax.set_xlabel("Avg Accuracy (%)")
    ax.set_xlim(0, 85)
    ax.set_title("Category Difficulty (avg across 6 completed models)")
    ax.invert_yaxis()
    for i, v in enumerate(rates):
        ax.text(v + 0.8, i, f"{v:.0f}%", va="center", fontsize=7.5)
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
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.set_aspect("equal")
    ax.axis("off")

    boxes = [
        (0.5, 4.5, 2.0, 1.0, "User Query\n(NL + history)", "#ecf0f1"),
        (3.5, 4.5, 3.0, 1.0, "LLM Agent\n(ReAct loop)", "#d5f5e3"),
        (3.5, 2.5, 3.0, 1.0, "Tool Router\n(12 tools)", "#d6eaf8"),
        (7.5, 4.5, 2.0, 1.0, "Response\n(NL + data)", "#fdebd0"),
        (7.5, 2.5, 2.0, 1.0, "Darwin Maps\nAPI (COGs)", "#fadbd8"),
        (3.5, 0.5, 3.0, 1.0, "Eval Harness\n(scoring)", "#e8daef"),
    ]
    for x, y, w, h, text, color in boxes:
        rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor=C_DARK, linewidth=1.2)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=8, fontweight="bold", color=C_DARK)

    arrows = [
        (2.5, 5.0, 1.0, 0),
        (6.5, 5.0, 1.0, 0),
        (5.0, 4.5, 0, -1.0),
        (5.0, 3.5, 0, 1.0),
        (6.5, 3.0, 1.0, 0),
        (7.5, 3.0, -1.0, 0),
        (5.0, 2.5, 0, -1.0),
    ]
    for x, y, dx, dy in arrows:
        ax.annotate("", xy=(x + dx, y + dy), xytext=(x, y),
                    arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.2))

    ax.text(3.0, 5.2, "query", fontsize=7, color=C_GRAY, ha="center")
    ax.text(7.0, 5.2, "answer", fontsize=7, color=C_GRAY, ha="center")
    ax.text(4.3, 3.9, "tool calls", fontsize=7, color=C_GRAY, rotation=90, va="center")
    ax.text(5.7, 3.9, "results", fontsize=7, color=C_GRAY, rotation=90, va="center")
    ax.text(7.0, 3.2, "API", fontsize=7, color=C_GRAY, ha="center")
    ax.text(4.3, 1.9, "log", fontsize=7, color=C_GRAY, rotation=90, va="center")

    ax.set_title("GeoNatureAgent Benchmark — System Architecture", fontsize=11, fontweight="bold", pad=10)
    fig.savefig(OUT / "fig6_architecture.pdf")
    fig.savefig(OUT / "fig6_architecture.png")
    plt.close(fig)
    print("  fig6_architecture")


# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 7: Token usage vs accuracy
# ═══════════════════════════════════════════════════════════════════════════
def fig7_tokens_vs_accuracy():
    # Exclude Maverick (0 tokens, infra failure)
    plot_models = models[:7]
    plot_acc = accuracy[:7]
    plot_tokens = tokens_k[:7]
    plot_colors = model_colors[:7]

    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    for i, m in enumerate(plot_models):
        ax.scatter(plot_tokens[i], plot_acc[i], s=80, c=plot_colors[i],
                   edgecolor=C_DARK, linewidth=0.5, zorder=3)
        if m == "DeepSeek V3.2":
            xytext = (-5, -12)
            ha = "right"
        elif m == "Claude Sonnet 4":
            xytext = (5, -10)
            ha = "left"
        else:
            xytext = (5, 5)
            ha = "left"
        ax.annotate(m, (plot_tokens[i], plot_acc[i]),
                    textcoords="offset points", xytext=xytext,
                    fontsize=7, color=C_DARK, ha=ha)
    ax.set_xlabel("Total Tokens (K)")
    ax.set_ylabel("Accuracy (%)")
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
    fig, ax = plt.subplots(figsize=(7, 5.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.set_aspect("equal")
    ax.axis("off")

    def _box(x, y, w, h, text, color, fs=7.5):
        rect = mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.08",
            facecolor=color, edgecolor=C_DARK, linewidth=1.0,
        )
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, fontweight="bold", color=C_DARK)

    def _arrow(x1, y1, x2, y2, label="", label_offset=(0, 4)):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.0))
        if label:
            mx, my = (x1 + x2) / 2 + label_offset[0], (y1 + y2) / 2 + label_offset[1] * 0.02
            ax.text(mx, my, label, fontsize=6.5, color=C_GRAY, ha="center", va="center")

    # ── Row 1: Input ──
    _box(0.3, 7.0, 2.0, 0.7, "Task\n(benchmark_v5.json)", "#ecf0f1")
    _box(3.8, 7.0, 2.4, 0.7, "Agent Output\n(answer, tools, actions)", "#d5f5e3")

    # ── Row 2: Check gate ──
    _arrow(1.3, 7.0, 3.5, 6.3)
    _arrow(5.0, 7.0, 5.0, 6.3)

    _box(1.0, 5.5, 7.0, 0.8, "8 Scoring Checks", "#d6eaf8", fs=9)

    # ── Row 3: Individual checks (two columns) ──
    checks_left = [
        "expected_tools  (recall = 1.0)",
        "expected_actions  (recall = 1.0)",
        "must_contain  (substring match)",
        "must_not_contain  (absence)",
    ]
    checks_right = [
        "numeric_accuracy  (label + %)",
        "chart_generated  (URL present)",
        "max_rounds  (budget gate)",
        "max_cost_usd  (budget gate)",
    ]
    for i, txt in enumerate(checks_left):
        yy = 5.1 - i * 0.45
        ax.text(1.2, yy, f"• {txt}", fontsize=6.5, color=C_DARK, va="center",
                fontfamily="monospace")
    for i, txt in enumerate(checks_right):
        yy = 5.1 - i * 0.45
        ax.text(5.2, yy, f"• {txt}", fontsize=6.5, color=C_DARK, va="center",
                fontfamily="monospace")

    # ── Row 4: Decision ──
    _arrow(4.5, 3.2, 4.5, 2.7)

    # Diamond shape for ALL pass decision
    diamond_x, diamond_y = 4.5, 2.3
    dw, dh = 0.8, 0.4
    diamond = plt.Polygon([
        (diamond_x, diamond_y + dh),
        (diamond_x + dw, diamond_y),
        (diamond_x, diamond_y - dh),
        (diamond_x - dw, diamond_y),
    ], closed=True, facecolor="#fef9e7", edgecolor=C_DARK, linewidth=1.0)
    ax.add_patch(diamond)
    ax.text(diamond_x, diamond_y, "ALL\npass?", fontsize=6.5, ha="center",
            va="center", fontweight="bold", color=C_DARK)

    # ── Row 5: Outputs ──
    # Yes branch
    _arrow(diamond_x - dw, diamond_y, 1.5, 1.3, "yes", label_offset=(-0.4, 0))
    _box(0.5, 0.7, 2.0, 0.6, "PASS\nbinary = 1", "#d5f5e3")

    # No branch
    _arrow(diamond_x + dw, diamond_y, 7.5, 1.3, "no", label_offset=(0.4, 0))
    _box(6.5, 0.7, 2.0, 0.6, "FAIL\nerror_category", "#fadbd8")

    # Partial credit (always computed)
    _arrow(diamond_x, diamond_y - dh, 4.5, 1.3)
    _box(3.2, 0.2, 2.6, 1.2, "Partial Credit\n(always computed)\n\n"
         "check_score\ntool_f1\nkeyword_coverage", "#e8daef", fs=6.5)

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
