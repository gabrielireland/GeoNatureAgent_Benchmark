"""Robustness checks: metadata-tool call rates on ALL runs, seed stability, rank stability, per-task tables, examples."""
import csv, json, os, ast, re, collections, random, math
P = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))  # repo root
S = json.load(open('data/selected_runs.json'))
NAME = {'exp_042_claude_sonnet4_v5_seeds5':'Claude Sonnet 4','exp_036_deepseek_v32_v5_seeds5':'DeepSeek V3.2','exp_039_glm5_v5_seeds5':'GLM-5',
 'exp_035_gemini25_pro_v5_seeds5':'Gemini 2.5 Pro','exp_040_qwen3_235b_v5_seeds5':'Qwen3-235B','exp_038_gpt_oss_120b_v5_seeds5':'GPT-OSS-120B',
 'exp_041_llama4_scout_v5_seeds5':'Llama 4 Scout','gpt4o_openrouter_v5':'GPT-4o','gemma3_openrouter_v5':'Gemma-3-27B'}
MODELS = ['Claude Sonnet 4','DeepSeek V3.2','GLM-5','Gemini 2.5 Pro','GPT-4o','Qwen3-235B','GPT-OSS-120B','Llama 4 Scout','Gemma-3-27B']
L = lambda x: x if isinstance(x,(list,dict)) else (ast.literal_eval(x) if x else [])
v5 = json.load(open(f'{P}/geoagentbench/cases/benchmark_v5.json')); v5 = v5['cases'] if isinstance(v5, dict) else v5
CASE = {c['id']: c for c in v5}
# ---- all runs with canonical pass label ----
pc = {(r['model'], r['case_id'], str(r['seed'])): r['passed'] == '1' for r in csv.DictReader(open(f'{P}/paper/final_results/per_case.csv'))}
runs = []
for exp, f in S.items():
    m = NAME[exp]
    for l in open(f):
        t = json.loads(l); k = (m, t['case_id'], str(t.get('seed')))
        if m in ('GPT-4o', 'Gemma-3-27B'): ok = t['passed'] in (True, 'True') or t['error_category'] == 'cost_exceeded'
        elif k in pc: ok = pc[k]
        else: continue                       # Claude: only the 2 published seeds
        called = [x.get('tool') for x in L(t.get('tools_called'))] or L(t.get('tools_used'))
        runs.append(dict(model=m, case=t['case_id'], seed=str(t.get('seed')), passed=ok, called=set(called), t=t))
print('runs', len(runs))
FAIL = {(r['model'], r['case_id'], r['seed']): r for r in csv.DictReader(open('data/failed_runs.csv'))}
out = {}
# ---- R1: metadata tool call rate on the tasks that require it, split by whether the prompt discourages that tool ----
META = {'get_legend': 'discouraged in prompt', 'list_layers': 'discouraged in prompt', 'get_layer_bounds': 'not mentioned in prompt', 'get_layer_info': 'not mentioned in prompt'}
rows = []
for tool, status in META.items():
    ids = [c['id'] for c in v5 if tool in c.get('expected_tools', [])]
    rs = [r for r in runs if r['case'] in ids]
    if not rs: continue
    rows.append([tool, status, len(ids), len(rs), sum(tool in r['called'] for r in rs), round(100*sum(tool in r['called'] for r in rs)/len(rs),1), round(100*sum(r['passed'] for r in rs)/len(rs),1)])
# baseline: analysis tools on analysis tasks
for tool in ('analyze_area', 'lookup_province', 'find_top_n', 'compare_areas'):
    ids = [c['id'] for c in v5 if tool in c.get('expected_tools', [])]; rs = [r for r in runs if r['case'] in ids]
    rows.append([tool, 'analysis tool (baseline)', len(ids), len(rs), sum(tool in r['called'] for r in rs), round(100*sum(tool in r['called'] for r in rs)/len(rs),1), round(100*sum(r['passed'] for r in rs)/len(rs),1)])
with open('tables/09_tool_call_rates.csv','w',newline='') as fh:
    w = csv.writer(fh); w.writerow(['expected_tool','prompt_status','tasks','runs','runs_calling_it','call_rate_pct','task_pass_rate_pct']); w.writerows(rows)
out['call_rates'] = rows
# ---- R2: seed stability of the family shares ----
fam = {r['subtype']: r['family'] for r in csv.DictReader(open('tables/01_subtypes.csv'))}
TM = [r for r in FAIL.values() if r['error_category'] == 'tool_missing']
bys = collections.defaultdict(collections.Counter)
for r in TM: bys[r['seed']][fam[r['subtype']]] += 1
seedrows = []
for s in sorted(bys): n = sum(bys[s].values()); seedrows.append([s, n] + [round(100*bys[s][f]/n,1) for f in sorted(set(fam.values()))])
with open('tables/10_family_share_by_seed.csv','w',newline='') as fh:
    w = csv.writer(fh); w.writerow(['seed','tool_missing_runs'] + sorted(set(fam.values()))); w.writerows(seedrows)
out['seed'] = seedrows
# ---- R3: rank stability (Kendall tau) ----
sens = list(csv.DictReader(open('tables/07_sensitivity_accuracy.csv')))
def tau(a, b):
    n = len(a); c = d = 0
    for i in range(n):
        for j in range(i+1, n):
            s = (a[i]-a[j])*(b[i]-b[j]); c += s > 0; d += s < 0
    return (c-d)/(n*(n-1)/2)
pub = [float(r['published_strict_acc']) for r in sens]
out['tau_metadata'] = round(tau(pub, [float(r['acc_if_metadata_from_prompt_counted']) for r in sens]), 3)
out['tau_any'] = round(tau(pub, [float(r['acc_if_any_tool_only_fail_counted']) for r in sens]), 3)
# ---- R4: per metadata task ----
mt = []
for c in v5:
    if not set(c.get('expected_tools', [])) & set(META): continue
    rs = [r for r in runs if r['case'] == c['id']]
    a2 = [r for r in rs if FAIL.get((r['model'], r['case'], r['seed']), {}).get('subtype') == 'A2_answered_metadata_from_prompt']
    a2ok = [r for r in a2 if FAIL[(r['model'], r['case'], r['seed'])]['other_checks_all_pass'] == '1']
    mt.append([c['id'], c['category'], '|'.join(c['expected_tools']), len(rs), sum(r['passed'] for r in rs), len(a2), len(a2ok), c['question'][:110]])
with open('tables/11_metadata_tasks.csv','w',newline='') as fh:
    w = csv.writer(fh); w.writerow(['case_id','category','expected_tools','runs','passed','A2_no_tool_from_prompt','A2_otherwise_correct','question']); w.writerows(mt)
out['meta_tasks'] = mt
# ---- R5: geological wording per case, 9 models ----
geo = [c for c in v5 if re.search(r'geolog', c['question'], re.I)]
gr = []
for c in geo:
    rs = [r for r in runs if r['case'] == c['id']]
    refuse = sum(1 for r in rs if re.search(r'geolog', str(r['t'].get('full_answer')), re.I) and re.search(r'absor', str(r['t'].get('full_answer')), re.I))
    gr.append([c['id'], len(rs), round(100*sum(r['passed'] for r in rs)/len(rs),1), refuse, c['question'][:100]])
allp = round(100*sum(r['passed'] for r in runs if r['case'] not in {c['id'] for c in geo})/sum(1 for r in runs if r['case'] not in {c['id'] for c in geo}),1)
with open('tables/12_geological_cases.csv','w',newline='') as fh:
    w = csv.writer(fh); w.writerow(['case_id','runs','pass_rate_pct','answers_contrasting_geological_vs_absorption','question']); w.writerows(gr)
out['geo'] = gr; out['geo_other_pass'] = allp; out['geo_pass'] = round(100*sum(r['passed'] for r in runs if r['case'] in {c['id'] for c in geo})/sum(1 for r in runs if r['case'] in {c['id'] for c in geo}),1)
# ---- R6: empty answers: what the trace says ----
emp = [r for r in TM if r['subtype'] == 'A1_empty_answer']
errs = collections.Counter()
tr = {(r['model'], r['case'], r['seed']): r['t'] for r in runs}
for r in emp:
    t = tr.get((r['model'], r['case_id'], r['seed']), {}); e = str(t.get('error') or '')
    errs[(r['model'], 'error field: ' + (e[:60] if e and e != 'None' else 'none'), 'output_tokens=' + str(t.get('output_tokens')))] += 1
out['empty'] = [[*k, v] for k, v in errs.most_common(12)]
# ---- R7: one verbatim example per subtype ----
random.seed(11); ex = {}
TMJ = [json.loads(l) for l in open('data/tool_missing_runs.jsonl')]
for st in sorted({r['subtype'] for r in TMJ}):
    pool = [r for r in TMJ if r['subtype'] == st and len(r['answer']) > 30] or [r for r in TMJ if r['subtype'] == st]
    r = random.choice(pool); ex[st] = dict(model=r['model'], case=r['case_id'], q=r['question'][:160], used=r['tools_called'], missing=r['missing'], a=re.sub(r'\s+', ' ', r['answer'])[:330])
out['examples'] = ex
# ---- R8: per-model accuracy on tool_selection tasks: published vs adjusted ----
ts = {c['id'] for c in v5 if c['category'] == 'tool_selection'}
tsr = []
for m in MODELS:
    rs = [r for r in runs if r['model'] == m and r['case'] in ts]
    flip = sum(1 for r in rs if not r['passed'] and FAIL.get((m, r['case'], r['seed']), {}).get('subtype') == 'A2_answered_metadata_from_prompt' and FAIL[(m, r['case'], r['seed'])]['other_checks_all_pass'] == '1')
    tsr.append([m, len(rs), round(100*sum(r['passed'] for r in rs)/len(rs),1), round(100*(sum(r['passed'] for r in rs)+flip)/len(rs),1)])
with open('tables/13_tool_selection_accuracy.csv','w',newline='') as fh:
    w = csv.writer(fh); w.writerow(['model','runs','published_pct','if_metadata_from_prompt_counted_pct']); w.writerows(tsr)
out['tool_selection'] = tsr
json.dump(out, open('tables/robustness.json','w'), indent=1, ensure_ascii=False)
for k in ('call_rates','seed','tau_metadata','tau_any','geo_pass','geo_other_pass','empty','tool_selection'): print(k, json.dumps(out[k], ensure_ascii=False))
