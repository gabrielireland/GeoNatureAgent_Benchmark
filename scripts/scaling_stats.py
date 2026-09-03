"""
Scale -> accuracy analysis for the five open-weight models with disclosed
parameter counts, computed directly from the per-seed leaderboard.

This backs the paper's "Quantifying the scale trend" paragraph and answers the
natural follow-up: "we ran three seeds -- shouldn't that change the p-value?"
It does not. The correlation's unit of analysis is the MODEL (n=5), so the
exact permutation test enumerates 5!=120 relabelings and the smallest attainable
two-sided p is 2/120=0.017. The three seeds are repeated measurements of the
SAME five models; pooling them (5x3=15 "points") would be pseudo-replication
(identical x repeated 3x, dependent rows) and would fabricate significance.

What the seeds legitimately buy is reported here:
  1. per-seed rank correlation (is rho=1.0 an averaging artifact? no),
  2. an EXACT enumeration over all 3^5=243 seed assignments (the five accuracy
     ranges are disjoint, so every assignment preserves the ranking), giving a
     distribution-free interval on Pearson r and the regression slope,
  3. an effect size (OLS of accuracy on log10 params) even though n=5 is small,
  4. the power threshold: the smallest n at which a perfect ranking would reach
     conventional significance (n=5, since 2/5!=0.017<0.05).

Pure standard library (no numpy / scipy) so it runs anywhere.

    python scripts/scaling_stats.py
"""

from __future__ import annotations

import csv
import math
import os
from itertools import permutations, product
from statistics import mean

LEADERBOARD = os.path.join("paper", "final_results", "leaderboard.csv")

# The five open-weight models with disclosed parameter counts (billions).
# `active` = parameters active per forward pass (MoE); sources in the model table.
MODEL_SPEC = {
    "Gemma-3-27B":   {"total": 27,  "active": 27.0},  # dense (no MoE): active == total
    "Llama 4 Scout": {"total": 109, "active": 17.0},
    "GPT-OSS-120B":  {"total": 120, "active": 5.1},
    "Qwen3-235B":    {"total": 235, "active": 22.0},
    "DeepSeek V3.2": {"total": 671, "active": 37.0},
}
SEED_COLUMNS = ["accuracy_seed_42", "accuracy_seed_1337", "accuracy_seed_2024"]


# --------------------------------------------------------------------------- #
# correlation primitives (no ties in our data, so ordinal ranks are exact)
# --------------------------------------------------------------------------- #
def rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0] * len(values)
    for position, i in enumerate(order):
        ranks[i] = position + 1
    return ranks


def pearson(x, y):
    mx, my = mean(x), mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else float("nan")


def spearman(x, y):
    return pearson(rank(x), rank(y))


def kendall_tau(x, y):
    """Kendall tau-a (no ties): (concordant - discordant) / (n choose 2)."""
    n = len(x)
    con = dis = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (x[i] - x[j]) * (y[i] - y[j])
            con += s > 0
            dis += s < 0
    return (con - dis) / (n * (n - 1) / 2)


def exact_perm_p(stat_fn, x, y):
    """Exact two-sided permutation p for any rank statistic: fraction of
    relabelings of y with |stat| >= |observed|. Returns (hits, total, p)."""
    observed = abs(stat_fn(x, y))
    hits = total = 0
    for perm in permutations(y):
        total += 1
        if abs(stat_fn(x, list(perm))) >= observed - 1e-12:
            hits += 1
    return hits, total, hits / total


def ols(x, y):
    """Simple OLS y = a + b*x. Returns (slope, intercept, r_squared)."""
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    b = sxy / sxx
    a = my - b * mx
    r = pearson(x, y)
    return b, a, r * r


def smallest_significant_n(alpha=0.05):
    """Smallest n at which a PERFECT rank correlation (rho=1) reaches two-sided
    permutation significance, i.e. 2/n! < alpha."""
    n, fact = 2, 2
    while 2 / fact >= alpha:
        n += 1
        fact *= n
    return n, fact, 2 / fact


def load_rows(path):
    with open(path, newline="") as f:
        return {r["model"]: r for r in csv.DictReader(f) if r["model"] in MODEL_SPEC}


# --------------------------------------------------------------------------- #
def main():
    rows = load_rows(LEADERBOARD)
    missing = set(MODEL_SPEC) - set(rows)
    if missing:
        raise SystemExit(f"leaderboard is missing rows for: {sorted(missing)}")

    models = sorted(MODEL_SPEC, key=lambda m: MODEL_SPEC[m]["total"])
    total = [MODEL_SPEC[m]["total"] for m in models]
    active = [MODEL_SPEC[m]["active"] for m in models]
    log_total = [math.log10(t) for t in total]
    mean_acc = [float(rows[m]["accuracy_mean"]) for m in models]
    seed_acc = {m: [float(rows[m][s]) for s in SEED_COLUMNS if rows[m][s] not in ("", None)]
                for m in models}

    print("=" * 70)
    print("SCALE -> ACCURACY ANALYSIS  (5 open-weight models, disclosed params)")
    print("=" * 70)
    print("\nmodel            total  active   mean%   per-seed% [42,1337,2024]   range")
    for m in models:
        s = seed_acc[m]
        print(f"{m:15s} {MODEL_SPEC[m]['total']:5d} {MODEL_SPEC[m]['active']:6.1f}"
              f"  {float(rows[m]['accuracy_mean'])*100:6.1f}   {[round(v*100,1) for v in s]}"
              f"   [{min(s)*100:.1f},{max(s)*100:.1f}]")

    # (1) per-seed reproducibility of the ranking
    print("\n[1] Per-seed rank correlation (is rho=1.0 an averaging artifact?)")
    for i, s in enumerate(SEED_COLUMNS):
        acc = [seed_acc[m][i] for m in models]
        print(f"    {s:20s}: Spearman rho={spearman(total, acc):+.3f}  "
              f"ranking_matches_size={rank(total)==rank(acc)}")

    # (2) aggregate correlations + exact permutation tests (the CORRECT n=5 test)
    print("\n[2] Aggregate correlations (unit = model, n=5)")
    rho_t = spearman(total, mean_acc)
    tau_t = kendall_tau(total, mean_acc)
    r_log = pearson(log_total, mean_acc)
    hs, ts, ps = exact_perm_p(spearman, total, mean_acc)
    hk, tk, pk = exact_perm_p(kendall_tau, total, mean_acc)
    print(f"    Spearman rho (total)      = {rho_t:+.3f}   exact perm p = {hs}/{ts} = {ps:.4f}")
    print(f"    Kendall  tau (total)      = {tau_t:+.3f}   exact perm p = {hk}/{tk} = {pk:.4f}")
    print(f"    Pearson  r (log10 total)  = {r_log:+.4f}")
    rho_a = spearman(active, mean_acc)
    tau_a = kendall_tau(active, mean_acc)
    print(f"    Spearman rho (active/MoE) = {rho_a:+.3f}   (architecture-sensitive)")
    print(f"    Kendall  tau (active/MoE) = {tau_a:+.3f}")

    # (3) exact enumeration over all seed assignments (distribution-free interval)
    print("\n[3] All 3^5 = 243 seed assignments (one seed's accuracy per model)")
    combos = list(product(*[range(len(seed_acc[m])) for m in models]))
    rhos, rs, slopes = [], [], []
    for c in combos:
        acc = [seed_acc[m][c[i]] for i, m in enumerate(models)]
        rhos.append(spearman(total, acc))
        rs.append(pearson(log_total, acc))
        slopes.append(ols(log_total, acc)[0] * 100)  # pp per decade of params
    frac_perfect = sum(abs(r - 1.0) < 1e-9 for r in rhos) / len(rhos)
    print(f"    assignments with Spearman rho = 1.0 : {frac_perfect*100:.1f}%  "
          f"({sum(abs(r-1.0)<1e-9 for r in rhos)}/{len(combos)})")
    print(f"    Pearson r (log10)   range: [{min(rs):.3f}, {max(rs):.3f}]  mean {mean(rs):.3f}")
    print(f"    slope (pp / decade) range: [{min(slopes):.1f}, {max(slopes):.1f}]  mean {mean(slopes):.1f}")
    print("    (ranges are exact, not bootstrapped: the 4 accuracy ranges are disjoint)")

    # (4) effect size on the aggregate
    b, a, r2 = ols(log_total, mean_acc)
    print("\n[4] Effect size  (OLS: accuracy ~ log10 total params)")
    print(f"    slope = {b*100:+.1f} pp per decade of parameters,  R^2 = {r2:.3f}")
    print(f"    (109B->671B is {math.log10(671/109):.2f} decades -> "
          f"predicted +{b*100*math.log10(671/109):.1f} pp; observed "
          f"+{(mean_acc[-1]-mean_acc[0])*100:.1f} pp)")

    # (5) power threshold
    n_sig, fact, p_sig = smallest_significant_n()
    print("\n[5] Power  (why n=4 cannot be significant, and what would be)")
    print(f"    smallest n where a PERFECT ranking reaches p<0.05: n={n_sig} "
          f"(2/{n_sig}! = 2/{fact} = {p_sig:.4f})")
    print(f"    at n=4 the floor is 2/24 = {2/24:.4f} -- unreachable below 0.05 by any data.")
    print("=" * 70)


if __name__ == "__main__":
    main()
