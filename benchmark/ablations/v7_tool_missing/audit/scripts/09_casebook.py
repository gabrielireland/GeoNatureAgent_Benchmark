"""Per-task casebook: question, expected tools, prompt stance, outcome of all runs, common tool flows, one full flow."""
import json, csv, collections, os, re, html, subprocess
P = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))  # repo root
v5 = json.load(open(f'{P}/geoagentbench/cases/benchmark_v5.json')); v5 = v5['cases'] if isinstance(v5, dict) else v5
CASE = {c['id']: c for c in v5}
RC = {(r['model'], r['case_id'], r['seed']): r for r in csv.DictReader(open('tables/14_root_cause_by_run.csv'))}
TM = {(r['model'], r['case_id'], r['seed']): r for r in map(json.loads, open('data/tool_missing_runs.jsonl'))}
FAIL = {(r['model'], r['case_id'], r['seed']): r for r in csv.DictReader(open('data/failed_runs.csv'))}
# all runs (pass + fail) with tool sequence, from traces
S = json.load(open('data/selected_runs.json'))
NAME = {'exp_042_claude_sonnet4_v5_seeds5':'Claude Sonnet 4','exp_036_deepseek_v32_v5_seeds5':'DeepSeek V3.2','exp_039_glm5_v5_seeds5':'GLM-5','exp_035_gemini25_pro_v5_seeds5':'Gemini 2.5 Pro','exp_040_qwen3_235b_v5_seeds5':'Qwen3-235B','exp_038_gpt_oss_120b_v5_seeds5':'GPT-OSS-120B','exp_041_llama4_scout_v5_seeds5':'Llama 4 Scout','gpt4o_openrouter_v5':'GPT-4o','gemma3_openrouter_v5':'Gemma-3-27B'}
pc = {(r['model'], r['case_id'], str(r['seed'])) for r in csv.DictReader(open(f'{P}/paper/final_results/per_case.csv'))}
ALL = collections.defaultdict(list)
for exp, f in S.items():
    m = NAME[exp]
    for l in open(f):
        t = json.loads(l); k = (m, t['case_id'], str(t.get('seed')))
        if m == 'Claude Sonnet 4' and k not in pc: continue
        seq = [x.get('tool') for x in (t.get('tools_called') or [])] if isinstance(t.get('tools_called'), list) else []
        ALL[t['case_id']].append(dict(model=m, seed=k[2], seq=seq, failed=k in FAIL, cat=FAIL.get(k, {}).get('error_category', 'passed')))
grp = lambda v: v.split(' ')[0]
by = collections.defaultdict(list)
for k, r in RC.items(): by[k[1]].append(r)
tasks = sorted(by, key=lambda c: -len(by[c]))
cum = 0; chosen = []
for c in tasks:
    chosen.append(c); cum += len(by[c])
    if cum / len(RC) >= 0.75: break
print('tasks chosen', len(chosen), 'covering', cum, 'of', len(RC))
def flow(t):
    out = []
    for i, call in enumerate(t.get('tools_called_detail') or []):
        args = json.dumps(call.get('input', {}), ensure_ascii=False)
        res = t['tool_results'][i] if i < len(t.get('tool_results') or []) else ''
        m = re.search(r"'content':\s*'(.{0,160})", res) or re.search(r'"content":\s*"(.{0,160})', res)
        out.append((call.get('tool'), args[:150], (m.group(1) if m else res[:160]).replace('\\n', ' ')))
    return out
cards = []
for c in chosen:
    case = CASE[c]; rs = by[c]; allr = ALL[c]
    vc = collections.Counter(r['verdict'] for r in rs); main = vc.most_common(1)[0][0]
    seqs = collections.Counter(' → '.join(x['seq']) or '(no tool executed)' for x in allr if x['failed'] and x['cat'] == 'tool_missing').most_common(3)
    pseqs = collections.Counter(' → '.join(x['seq']) or '(none)' for x in allr if not x['failed']).most_common(2)
    # representative: run with the main verdict, prefer a strong model
    pref = ['Claude Sonnet 4','DeepSeek V3.2','GLM-5','Gemini 2.5 Pro','GPT-4o','Qwen3-235B','GPT-OSS-120B','Llama 4 Scout','Gemma-3-27B']
    rep = sorted([r for r in rs if r['verdict'] == main], key=lambda r: pref.index(r['model']))[0]
    t = TM[(rep['model'], rep['case_id'], rep['seed'])]
    cards.append(dict(case=c, cat=case['category'], q=case['question'], exp=case['expected_tools'], note=case.get('ground_truth_notes', ''),
                      runs=len(allr), passed=sum(not x['failed'] for x in allr), tm=len(rs), verdicts=vc.most_common(), main=main,
                      reason=rep['reason'], seqs=seqs, pseqs=pseqs, rep_model=rep['model'], rep_seed=rep['seed'], flow=flow(t),
                      answer=re.sub(r'\s+', ' ', t['answer'])[:420], otherwise=sum(r['other_checks_all_pass'] == '1' for r in rs)))
json.dump(cards, open('tables/casebook.json', 'w'), indent=1, ensure_ascii=False)
print(collections.Counter(grp(c['main']) + ' ' + c['main'] for c in cards).most_common())
