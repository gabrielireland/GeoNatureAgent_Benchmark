"""v6 figure: comparison accuracy vs. value-gap.

Backs the R1-W1 close-value discussion. Reads paper/final_results/v6_gap.csv
(written by scripts/aggregate_v6.py) and produces two panels:

  (left)  pooled comparison accuracy vs. the ground-truth value gap, under BOTH
          raw and capability scoring. The point is the NON-trend: accuracy does
          not rise with the gap, and the 45.1 pp CONTROL is no easier than the
          close cases under raw scoring -- so the difficulty is not near-equal
          numeric discrimination.
  (right) per-model comparison accuracy, capability vs. raw. The gap between the
          two bars is round/budget exhaustion (models timing out while composing
          repeated analyze_area calls over the Portugal layer).

    python3 paper/generate_v6_figure.py   # -> paper/figures/fig_v6_comparison.{pdf,png}
"""
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
RESULTS = Path(__file__).parent / "final_results"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman", "STIX Two Text", "DejaVu Serif", "Times New Roman"],
    "mathtext.fontset": "stix",
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "axes.edgecolor": "#333333", "axes.linewidth": 0.8, "axes.labelcolor": "#222222",
    "xtick.labelsize": 9, "ytick.labelsize": 9,
    "legend.fontsize": 8.5, "legend.frameon": False,
    "figure.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.05,
})

C_RAW = "#d95f02"   # orange  = raw (strict)
C_CAP = "#7570b3"   # purple  = capability (gates excused)


def load_gap():
    with (RESULTS / "v6_gap.csv").open() as f:
        return list(csv.DictReader(f))


def load_leaderboard():
    with (RESULTS / "leaderboard_v6.csv").open() as f:
        rows = list(csv.DictReader(f))
    # short names for the x axis, in the CSV's (capability-sorted) order
    pretty = {
        "openrouter/anthropic/claude-sonnet-4": "Claude S4",
        "vertex_ai/deepseek-ai/deepseek-v3.2-maas": "DeepSeek",
        "vertex_ai/zai-org/glm-5-maas": "GLM-5",
        "vertex_ai/gemini-2.5-pro": "Gemini",
        "vertex_ai/qwen/qwen3-235b-a22b-instruct-2507-maas": "Qwen3",
        "openrouter/openai/gpt-4o": "GPT-4o",
        "vertex_ai/openai/gpt-oss-120b-maas": "GPT-OSS",
        "vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas": "Llama4",
        "openrouter/google/gemma-3-27b-it": "Gemma3",
    }
    for r in rows:
        r["name"] = pretty.get(r["model"], r["model"])
    return rows


def main():
    gap = load_gap()
    lb = load_leaderboard()

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(9, 3.6))

    # ---- LEFT: accuracy vs value gap ----------------------------------------
    gaps = [float(r["gap_pp"]) for r in gap]
    raw = [100 * float(r["acc_raw"]) for r in gap]
    cap = [100 * float(r["acc_capability"]) for r in gap]
    order = np.argsort(gaps)
    gaps = [gaps[i] for i in order]
    raw = [raw[i] for i in order]
    cap = [cap[i] for i in order]

    axL.plot(gaps, cap, "-o", color=C_CAP, ms=5, lw=1.4, label="capability (gates excused)")
    axL.plot(gaps, raw, "-o", color=C_RAW, ms=5, lw=1.4, label="raw (strict pass)")
    # mark the control
    ctrl_x = max(gaps)
    axL.axvline(ctrl_x, color="#999999", ls=":", lw=0.9)
    axL.annotate("large-gap\ncontrol (V6\\_05)", xy=(ctrl_x, 8), xytext=(-8, 0),
                 textcoords="offset points", ha="right", va="bottom",
                 fontsize=8, color="#555555")
    axL.set_xscale("symlog", linthresh=4)
    axL.set_xlabel("Ground-truth value gap (percentage points)", fontweight="bold")
    axL.set_ylabel("Comparison accuracy (\\%)", fontweight="bold")
    axL.set_ylim(-4, 100)
    axL.set_title("Difficulty does not track value gap", fontsize=10)
    axL.set_xticks([0.6, 1.2, 2.1, 3.2, 45.1])
    axL.set_xticklabels(["0.6", "1.2", "2.1", "3.2", "45"])
    axL.legend(loc="upper center")
    axL.spines["top"].set_visible(False)
    axL.spines["right"].set_visible(False)

    # ---- RIGHT: per-model comparison cap vs raw -----------------------------
    names = [r["name"] for r in lb]
    ccap = [100 * float(r["comparison_cap"]) for r in lb]
    craw = [100 * float(r["comparison_raw"]) for r in lb]
    y = np.arange(len(names))[::-1]
    h = 0.38
    axR.barh(y + h / 2, ccap, height=h, color=C_CAP, label="capability")
    axR.barh(y - h / 2, craw, height=h, color=C_RAW, label="raw")
    axR.set_yticks(y)
    axR.set_yticklabels(names)
    axR.set_xlabel("Comparison accuracy (\\%)", fontweight="bold")
    axR.set_xlim(0, 100)
    axR.set_title("Cap.$-$raw gap = round exhaustion", fontsize=10)
    axR.legend(loc="lower right")
    axR.spines["top"].set_visible(False)
    axR.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(OUT / "fig_v6_comparison.pdf")
    fig.savefig(OUT / "fig_v6_comparison.png")
    print("wrote", OUT / "fig_v6_comparison.pdf")


if __name__ == "__main__":
    main()
