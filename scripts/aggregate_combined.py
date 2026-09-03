"""Combined 103-task leaderboard: v5 main suite (93) + v6 expansion (10).

Answers the reviewer ask that new tasks be INCLUDED in the headline evaluation,
not only probed separately. No new runs: composes the two existing result sets.

Metric: capability, defined per suite exactly as published --
  * v5: the ``passed`` column of paper/final_results/per_case.csv
        (cost gate excused -- reproduces the 93-task leaderboard exactly);
  * v6: pass OR failure excused by a budget/round gate
        (aggregate_v6.py's ``cap_pass`` -- reproduces Table tab:v6 exactly).
Per model and seed, combined accuracy = (v5 passes + v6 passes) / 103; reported
as per-seed mean +- sd over the seeds present in both suites (Claude Sonnet 4 has
two v5 samples; they are paired with its first two v6 seeds and noted as such).

Writes, under paper/final_results/:
  * leaderboard_v5plus6.csv  -- per-model combined capability (mean, sd, per-seed)
  * v6_table.tex             -- REGENERATED with an extra "103-task comb." column
                                (drop-in replacement for the paper's \\input)

    python3 -m scripts.aggregate_combined
"""
import csv
import glob
import json
import pathlib
import statistics
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "final_results"

GATE = {"rounds_exceeded", "cost_exceeded"}

PRETTY = {
    "openrouter/anthropic/claude-sonnet-4": "Claude Sonnet 4",
    "claude-sonnet-4-20250514": "Claude Sonnet 4",
    "vertex_ai/deepseek-ai/deepseek-v3.2-maas": "DeepSeek V3.2",
    "vertex_ai/zai-org/glm-5-maas": "GLM-5",
    "vertex_ai/gemini-2.5-pro": "Gemini 2.5 Pro",
    "vertex_ai/qwen/qwen3-235b-a22b-instruct-2507-maas": "Qwen3-235B",
    "openrouter/openai/gpt-4o": "GPT-4o",
    "vertex_ai/openai/gpt-oss-120b-maas": "GPT-OSS-120B",
    "vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas": "Llama 4 Scout",
    "openrouter/google/gemma-3-27b-it": "Gemma-3-27B",
}


def cap_pass(r):
    return bool(r.get("passed")) or (r.get("error_category") in GATE)


def v5_passes_by_model_seed():
    """{model: {seed: n_passed}} from the committed per-case matrix (93 cases/seed).

    GPT-4o and Gemma-3-27B are not in per_case.csv (the 7->9 fold-in updated only
    leaderboard/per_category), so their per-case outcomes are read from the run
    dirs using the canonical capability rule (compile_final_results._capability_passed).
    """
    out = defaultdict(lambda: defaultdict(int))
    counts = defaultdict(lambda: defaultdict(int))
    with open(OUT / "per_case.csv") as f:
        for row in csv.DictReader(f):
            m, s = row["model"], row["seed"]
            counts[m][s] += 1
            out[m][s] += int(row["passed"])
    import scripts.compile_final_results as C
    for name, run_dir in (("GPT-4o", "run_gpt4o_openrouter_v5"),
                          ("Gemma-3-27B", "run_gemma3_openrouter_v5")):
        if name in out:
            continue
        for line in open(ROOT / "results" / run_dir / "results.jsonl"):
            r = json.loads(line)
            s = str(r["seed"])
            counts[name][s] += 1
            out[name][s] += int(C._capability_passed(r))
    for m in counts:
        for s, n in counts[m].items():
            assert n == 93, f"{m} seed {s}: {n} v5 cases (expected 93)"
    return out


def v6_cap_by_model_seed():
    """{model: {seed: n_cap_passed}} from results/run_v6_*/results.jsonl (10 cases/seed)."""
    out = defaultdict(lambda: defaultdict(int))
    counts = defaultdict(lambda: defaultdict(int))
    for path in glob.glob(str(ROOT / "results" / "run_v6_*" / "results.jsonl")):
        for line in open(path):
            r = json.loads(line)
            m = PRETTY.get(r["model_id"], r["model_id"])
            s = str(r["seed"])
            counts[m][s] += 1
            out[m][s] += int(cap_pass(r))
    for m in counts:
        for s, n in counts[m].items():
            assert n == 10, f"{m} seed {s}: {n} v6 cases (expected 10)"
    return out


def main():
    v5 = v5_passes_by_model_seed()
    v6 = v6_cap_by_model_seed()

    rows = []
    for model in v6:
        if model not in v5:
            continue
        v5_seeds = sorted(v5[model])
        v6_seeds = sorted(v6[model])
        # Pair seeds positionally; identical {42,1337,2024} everywhere except
        # Claude's two unlabeled-equivalent v5 samples (paired with first two v6 seeds).
        pairs = list(zip(v5_seeds, v6_seeds))
        per_seed = [(v5[model][a] + v6[model][b]) / 103.0 for a, b in pairs]
        mean = sum(per_seed) / len(per_seed)
        sd = statistics.stdev(per_seed) if len(per_seed) > 1 else 0.0
        v5_mean = sum(v5[model][s] for s in v5_seeds) / len(v5_seeds) / 93.0
        rows.append({
            "model": model,
            "n_seed_pairs": len(pairs),
            "v5_93task_capability": round(v5_mean, 4),
            "combined_103task_capability": round(mean, 4),
            "combined_103task_sd": round(sd, 4),
            "per_seed": ";".join(f"{p:.4f}" for p in per_seed),
            "note": "v6 leg uses capability scoring (budget/round gates excused), as in tab:v6",
        })
    rows.sort(key=lambda r: -r["combined_103task_capability"])

    with open(OUT / "leaderboard_v5plus6.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT / "leaderboard_v5plus6.csv")
    for r in rows:
        print(f"  {r['model']:16s} v5={r['v5_93task_capability']*100:5.1f}%  "
              f"combined={r['combined_103task_capability']*100:5.1f}% +- {r['combined_103task_sd']*100:.1f}")

    # ---- regenerate v6_table.tex with the combined column -------------------
    v6_rows = list(csv.DictReader(open(OUT / "leaderboard_v6.csv")))
    comb = {r["model"]: r for r in rows}
    short = {  # leaderboard_v6.csv keys models by raw model_id
        mid: PRETTY.get(mid, mid) for mid in [r["model"] for r in v6_rows]
    }
    v6_rows.sort(key=lambda r: -float(r["accuracy_capability"]))
    lines = [
        "% AUTO-GENERATED by scripts/aggregate_combined.py -- do not edit by hand.",
        "\\begin{table}[ht]",
        "  \\caption{v6 expansion (10 comparison-heavy tasks, 3 seeds) and the combined"
        " 103-task suite. \\emph{Cap.}\\ is capability scoring (budget/round gates excused,"
        " as in the v5 leaderboard); \\emph{raw} is strict pass. \\emph{103-task comb.}\\ is"
        " capability accuracy over the full v5+v6 suite (per-seed mean), the inclusive"
        " headline metric for this paper.}",
        "  \\label{tab:v6}",
        "  \\centering",
        "  \\small",
        "  \\begin{tabular}{lrrrr}",
        "    \\toprule",
        "    \\textbf{Model} & \\textbf{Cap.} & \\textbf{Raw} & \\textbf{Comp.\\ cap/raw} & \\textbf{103-task comb.} \\\\",
        "    \\midrule",
    ]
    for r in v6_rows:
        name = short[r["model"]]
        c = comb.get(name)
        comb_txt = f"${c['combined_103task_capability']*100:.1f}\\%$" if c else "---"
        lines.append(
            f"    {name} & ${float(r['accuracy_capability'])*100:.0f}\\%$"
            f" & ${float(r['accuracy_raw'])*100:.0f}\\%$"
            f" & ${float(r['comparison_cap'])*100:.0f}/{float(r['comparison_raw'])*100:.0f}\\%$"
            f" & {comb_txt} \\\\"
        )
    lines += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}", ""]
    (OUT / "v6_table.tex").write_text("\n".join(lines))
    print("wrote", OUT / "v6_table.tex", "(with combined column)")


if __name__ == "__main__":
    main()
