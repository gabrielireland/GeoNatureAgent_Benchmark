"""v5.1 re-scoring WITHOUT new runs, from existing traces.
V0 published. V1 = fix what is ours and re-scorable:
  - metadata / coverage tasks (P1, P2, S1): pass if the answer passed every other check (answer-correct scoring)
  - prompt-mandated alternative routes (P3): pass if every other check passed
  - drop invalid tasks (wrong ground truth / impossible tool: V5_47, V5_73, V5_85)
  - drop infrastructure failures (timeouts / provider errors) from the denominator
V2 = V1 + drop the 8 'geological storage' tasks until they are reworded and re-run.
Not re-scorable (needs re-runs): neutral prompt, parser for text tool calls, list_layers fix, reworded tasks."""
import json, csv, os, collections, statistics as st, re
P = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))  # repo root
S = json.load(open('data/selected_runs.json'))
NAME = {'exp_042_claude_sonnet4_v5_seeds5':'Claude Sonnet 4','exp_036_deepseek_v32_v5_seeds5':'DeepSeek V3.2','exp_039_glm5_v5_seeds5':'GLM-5','exp_035_gemini25_pro_v5_seeds5':'Gemini 2.5 Pro','exp_040_qwen3_235b_v5_seeds5':'Qwen3-235B','exp_038_gpt_oss_120b_v5_seeds5':'GPT-OSS-120B','exp_041_llama4_scout_v5_seeds5':'Llama 4 Scout','gpt4o_openrouter_v5':'GPT-4o','gemma3_openrouter_v5':'Gemma-3-27B'}
MODELS = list(NAME.values()); MODELS = ['Claude Sonnet 4','DeepSeek V3.2','GLM-5','Gemini 2.5 Pro','GPT-4o','Qwen3-235B','GPT-OSS-120B','Llama 4 Scout','Gemma-3-27B']
pc = {(r['model'], r['case_id'], str(r['seed'])): r['passed'] == '1' for r in csv.DictReader(open(f'{P}/paper/final_results/per_case.csv'))}
RC = {(r['model'], r['case_id'], r['seed']): r for r in csv.DictReader(open('tables/16_root_cause_final.csv'))}
v5 = json.load(open(f'{P}/geoagentbench/cases/benchmark_v5.json')); v5 = v5['cases'] if isinstance(v5, dict) else v5
GEO = {c['id'] for c in v5 if re.search(r'geolog', c['question'], re.I)}
INVALID = {'V5_47_error_recovery_fallback_indicator', 'V5_73_deep_dive_municipality', 'V5_85_multi_layer_municipality_lorca'}
runs = []
for exp, f in S.items():
    m = NAME[exp]
    for l in open(f):
        t = json.loads(l); k = (m, t['case_id'], str(t.get('seed')))
        if m in ('GPT-4o', 'Gemma-3-27B'): ok = t['passed'] in (True, 'True') or t['error_category'] == 'cost_exceeded'
        elif k in pc: ok = pc[k]
        else: continue
        rc = RC.get(k)
        v1 = ok or (rc is not None and rc['code'] in ('P1', 'P2', 'S1', 'P3') and rc['other_checks_all_pass'] == '1')
        infra = rc is not None and rc['code'] == 'H2'
        runs.append(dict(model=m, case=t['case_id'], seed=k[2], v0=ok, v1=v1, infra=infra))
def acc(rows, key, drop=lambda r: False):
    seeds = collections.defaultdict(list)
    for r in rows:
        if drop(r): continue
        seeds[r['seed']].append(r[key])
    a = [100 * sum(v) / len(v) for v in seeds.values()]
    return st.mean(a), (st.stdev(a) if len(a) > 1 else 0.0), sum(len(v) for v in seeds.values())
d1 = lambda r: r['case'] in INVALID or r['infra']
d2 = lambda r: d1(r) or r['case'] in GEO
out = []
for m in MODELS:
    R = [r for r in runs if r['model'] == m]
    a0 = acc(R, 'v0'); a1 = acc(R, 'v1', d1); a2 = acc(R, 'v1', d2)
    out.append([m, f'{a0[0]:.1f} ± {a0[1]:.1f}', f'{a1[0]:.1f} ± {a1[1]:.1f}', f'{a2[0]:.1f} ± {a2[1]:.1f}', round(a1[0]-a0[0],1), a0[2], a1[2], a2[2]])
with open('tables/19_rescored_leaderboard.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['model','V0_published','V1_rescored','V2_rescored_no_geological_tasks','V1_minus_V0','runs_V0','runs_V1','runs_V2']); w.writerows(out)
for o in out: print(o)
# new failure picture under V1
F1 = [r for r in runs if not d1(r) and not r['v1']]
allf = len(F1); tmv1 = sum(1 for r in F1 if (r['model'], r['case'], r['seed']) in RC)
print('V1 failures', allf, 'of', sum(1 for r in runs if not d1(r)), '| still tool_missing', tmv1, f'({100*tmv1/allf:.1f}% of failures)')
codes = collections.Counter(RC[(r['model'], r['case'], r['seed'])]['code'] for r in F1 if (r['model'], r['case'], r['seed']) in RC)
print('remaining tool_missing by cause', codes.most_common())
# tool selection category under V1
ts = {c['id'] for c in v5 if c['category'] == 'tool_selection'}
print('tool_selection V0/V1 by model:', [(m, round(acc([r for r in runs if r['model']==m and r['case'] in ts],'v0')[0],1), round(acc([r for r in runs if r['model']==m and r['case'] in ts],'v1',d1)[0],1)) for m in MODELS])
# re-run cost estimate from published per-seed cost
lb = {r['model']: float(r['cost_per_seed_mean']) for r in csv.DictReader(open(f'{P}/paper/final_results/leaderboard.csv'))}
print('re-run cost, 3 seeds all models (list price, USD):', round(3*sum(lb.values()),0), {m: round(3*v,1) for m, v in lb.items()})
json.dump(dict(V1_failures=allf, still_tool_missing=tmv1, remaining=codes.most_common()), open('tables/rescore_summary.json','w'), indent=1)
