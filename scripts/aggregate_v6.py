"""Aggregate the v6 expansion runs into a leaderboard + a drop-in LaTeX table.

Reads every ``results/run_v6_*/results.jsonl`` and writes, under
``paper/final_results/``:

  * ``leaderboard_v6.csv``      — per-model metrics (RAW and capability)
  * ``v6_per_case.csv``         — per-model x per-case raw pass matrix
  * ``v6_gap.csv``              — comparison accuracy by value-gap (for the figure)
  * ``v6_table.tex``            — a ready ``\input{}`` LaTeX table fragment

Why two accuracy columns. The paper's v5 leaderboard uses *capability* scoring:
a run that fails ONLY on a budget/round gate (``cost_exceeded`` / ``rounds_exceeded``)
is not counted as a capability failure. For the v6 comparison tasks this gate is
load-bearing -- several models exhaust their turns composing repeated
``analyze_area`` calls over the Portugal layer -- so capability alone paints an
over-rosy picture (e.g. Claude's comparison accuracy is 1.000 capability but
0/18 raw). We therefore emit BOTH so the paper can report them side by side.

This is the workflow fix: step 3 now produces a LaTeX fragment, not just a CSV,
so "get the results into the paper" is a one-line \input rather than a retype.

    python3 scripts/aggregate_v6.py
"""
import json
import glob
import csv
import collections
import pathlib

GATE = {"rounds_exceeded", "cost_exceeded"}  # capability-scoring: excused, not a capability failure

# Comparison cases and their ground-truth value gaps (percentage points).
GAP = {
    "V6_02_comparison_veryclose_coniferous": 0.6,
    "V6_01_comparison_close_broadleaf": 1.2,
    "V6_03_comparison_moderate_shrubland": 2.1,
    "V6_10_sum_compare_total_forest": 3.1,
    "V6_04_comparison_moderate_broadleaf": 3.2,
    "V6_05_comparison_control_largegap": 45.1,
}

# Short, paper-friendly model names keyed by the raw model_id in the run rows.
PRETTY = {
    "openrouter/anthropic/claude-sonnet-4": "Claude Sonnet 4",
    "vertex_ai/deepseek-ai/deepseek-v3.2-maas": "DeepSeek V3.2",
    "vertex_ai/zai-org/glm-5-maas": "GLM-5",
    "vertex_ai/gemini-2.5-pro": "Gemini 2.5 Pro",
    "vertex_ai/qwen/qwen3-235b-a22b-instruct-2507-maas": "Qwen3-235B",
    "openrouter/openai/gpt-4o": "GPT-4o",
    "vertex_ai/openai/gpt-oss-120b-maas": "GPT-OSS-120B",
    "vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas": "Llama 4 Scout",
    "openrouter/google/gemma-3-27b-it": "Gemma-3-27B",
}

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "final_results"


def cap_pass(r):
    """Capability outcome: a genuine pass, OR a failure excused by a budget/round gate."""
    return bool(r.get("passed")) or (
        not r.get("passed") and r.get("error_category") in GATE
    )


def load():
    by = collections.defaultdict(lambda: collections.defaultdict(list))  # model -> case -> [rows]
    for f in glob.glob(str(ROOT / "results" / "run_v6_*" / "results.jsonl")):
        for line in open(f):
            if not line.strip():
                continue
            r = json.loads(line)
            by[r["model_id"]][r["case_id"]].append(r)
    return by


def main():
    by = load()
    OUT.mkdir(parents=True, exist_ok=True)
    comp_cases = list(GAP)

    rows = []
    for m, cases in by.items():
        allr = [r for c in cases.values() for r in c]
        n = len(allr)
        npass = sum(1 for r in allr if r.get("passed"))
        ncap = sum(1 for r in allr if cap_pass(r))
        comp = [r for c in comp_cases for r in cases.get(c, [])]
        ctrl = cases.get("V6_05_comparison_control_largegap", [])
        rows.append({
            "model": m,
            "pretty": PRETTY.get(m, m),
            "n_obs": n,
            "acc_raw": npass / n if n else 0,
            "acc_capability": ncap / n if n else 0,
            "comparison_raw": (sum(bool(r.get("passed")) for r in comp) / len(comp)) if comp else 0,
            "comparison_cap": (sum(cap_pass(r) for r in comp) / len(comp)) if comp else 0,
            "control_raw": (sum(bool(r.get("passed")) for r in ctrl) / len(ctrl)) if ctrl else 0,
            "control_cap": (sum(cap_pass(r) for r in ctrl) / len(ctrl)) if ctrl else 0,
        })
    rows.sort(key=lambda d: -d["acc_capability"])

    # 1. leaderboard_v6.csv (keeps the capability columns the paper build referenced,
    #    now alongside the honest raw columns).
    lb = OUT / "leaderboard_v6.csv"
    with lb.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "n_obs", "accuracy_capability", "accuracy_raw",
                    "comparison_cap", "comparison_raw", "control_V6_05_cap",
                    "control_V6_05_raw", "note"])
        for d in rows:
            w.writerow([d["model"], d["n_obs"], f"{d['acc_capability']:.3f}",
                        f"{d['acc_raw']:.3f}", f"{d['comparison_cap']:.3f}",
                        f"{d['comparison_raw']:.3f}", f"{d['control_cap']:.3f}",
                        f"{d['control_raw']:.3f}",
                        "capability excuses cost/rounds gates; raw is strict pass"])
    print("wrote", lb)

    # 2. v6_per_case.csv — raw pass fraction per model x case.
    all_cases = sorted({c for cs in by.values() for c in cs})
    pc = OUT / "v6_per_case.csv"
    with pc.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model"] + all_cases)
        for d in rows:
            cs = by[d["model"]]
            w.writerow([d["pretty"]] + [
                f"{sum(bool(r.get('passed')) for r in cs.get(c, []))/len(cs[c]):.2f}"
                if cs.get(c) else "" for c in all_cases])
    print("wrote", pc)

    # 3. v6_gap.csv — comparison accuracy by value gap, pooled over all models/seeds.
    gp = OUT / "v6_gap.csv"
    with gp.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "gap_pp", "n", "acc_raw", "acc_capability"])
        for c, g in sorted(GAP.items(), key=lambda x: x[1]):
            obs = [r for m in by for r in by[m].get(c, [])]
            if not obs:
                continue
            w.writerow([c, g, len(obs),
                        f"{sum(bool(r.get('passed')) for r in obs)/len(obs):.3f}",
                        f"{sum(cap_pass(r) for r in obs)/len(obs):.3f}"])
    print("wrote", gp)

    # 4. v6_table.tex — drop-in LaTeX table (workflow fix: paper \input's this).
    tex = OUT / "v6_table.tex"
    lines = [
        "% AUTO-GENERATED by scripts/aggregate_v6.py -- do not edit by hand.",
        "\\begin{table}[ht]",
        "  \\caption{v6 expansion (10 comparison-heavy tasks, 3 seeds). "
        "\\emph{Cap.}\\ is capability scoring (budget/round gates excused, as in the "
        "v5 leaderboard); \\emph{raw} is strict pass. The two comparison columns diverge "
        "because several models exhaust their turn budget composing repeated "
        "\\texttt{analyze\\_area} calls over the Portugal layer.}",
        "  \\label{tab:v6}",
        "  \\centering",
        "  \\small",
        "  \\begin{tabular}{lrrrr}",
        "    \\toprule",
        "    \\textbf{Model} & \\textbf{Cap.} & \\textbf{Raw} & "
        "\\textbf{Comp.\\ cap/raw} & \\textbf{Ctrl.\\ cap/raw} \\\\",
        "    \\midrule",
    ]
    for d in rows:
        lines.append(
            f"    {d['pretty']} & ${100*d['acc_capability']:.0f}\\%$ & "
            f"${100*d['acc_raw']:.0f}\\%$ & "
            f"${100*d['comparison_cap']:.0f}/{100*d['comparison_raw']:.0f}\\%$ & "
            f"${100*d['control_cap']:.0f}/{100*d['control_raw']:.0f}\\%$ \\\\"
        )
    lines += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}", ""]
    tex.write_text("\n".join(lines))
    print("wrote", tex)


if __name__ == "__main__":
    main()
