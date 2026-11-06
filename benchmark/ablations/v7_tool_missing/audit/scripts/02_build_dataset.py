"""Build the failed-run dataset (1,429 runs) and sub-classify every `tool_missing` failure.

Labels (passed / error_category) come from the canonical paper data:
  - 7 models: GeoNatureAgent_Benchmark/paper/final_results/per_case.csv
  - GPT-4o, Gemma-3-27B: results/run_{gpt4o,gemma3}_openrouter_v5 with the capability rule
    (a run that fails ONLY on cost is excused), as in scripts/add_models_to_leaderboard.py.
Behaviour (tools called, tool results, answer) comes from the raw traces in data/selected_runs.json.
"""
import json, csv, os, re, ast, collections
P = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))  # repo root
S = json.load(open('data/selected_runs.json'))

def L(x):
    if isinstance(x, (list, dict)): return x
    try: return ast.literal_eval(x)
    except Exception: return []

# ---- case metadata ----
cases = {c['id']: c for c in json.load(open(f'{P}/geoagentbench/cases/benchmark_v5.json'))['cases']} \
    if isinstance(json.load(open(f'{P}/geoagentbench/cases/benchmark_v5.json')), dict) else \
    {c['id']: c for c in json.load(open(f'{P}/geoagentbench/cases/benchmark_v5.json'))}

NAME = {'exp_042_claude_sonnet4_v5_seeds5': 'Claude Sonnet 4', 'exp_036_deepseek_v32_v5_seeds5': 'DeepSeek V3.2',
        'exp_039_glm5_v5_seeds5': 'GLM-5', 'exp_035_gemini25_pro_v5_seeds5': 'Gemini 2.5 Pro',
        'exp_040_qwen3_235b_v5_seeds5': 'Qwen3-235B', 'exp_038_gpt_oss_120b_v5_seeds5': 'GPT-OSS-120B',
        'exp_041_llama4_scout_v5_seeds5': 'Llama 4 Scout', 'gpt4o_openrouter_v5': 'GPT-4o',
        'gemma3_openrouter_v5': 'Gemma-3-27B'}

# ---- traces indexed by (model, case, seed) ----
trace = {}
for exp, f in S.items():
    for l in open(f):
        r = json.loads(l); trace[(NAME[exp], r['case_id'], str(r.get('seed')))] = r

# ---- canonical failure labels ----
failed = []
for r in csv.DictReader(open(f'{P}/paper/final_results/per_case.csv')):
    if r['passed'] == '0':
        failed.append(dict(model=r['model'], case_id=r['case_id'], seed=str(r['seed']), category=r['category'],
                           error_category=r['error_category'], check_score=float(r['check_score']),
                           rounds=int(r['rounds']), label_source='per_case.csv'))
for exp in ('gpt4o_openrouter_v5', 'gemma3_openrouter_v5'):
    for l in open(S[exp]):
        r = json.loads(l)
        if r['passed'] in (True, 'True'): continue
        if r['error_category'] == 'cost_exceeded': continue      # capability rule: cost-only fails excused
        failed.append(dict(model=NAME[exp], case_id=r['case_id'], seed=str(r.get('seed')),
                           category=(r.get('metadata') or {}).get('category', ''), error_category=r['error_category'],
                           check_score=float(r['check_score']), rounds=int(r['rounds']), label_source='results.jsonl'))
print('failed runs', len(failed), collections.Counter(x['error_category'] for x in failed).most_common())

# ---- sub-classification helpers ----
GEO = {'lookup_province', 'lookup_municipality'}
ANALYSIS = {'analyze_area', 'analyze_multi_layer', 'compare_areas', 'find_top_n', 'query_erosion_stats',
            'create_buffer', 'select_features_by_spatial_relationship', 'get_centroids'}
DISPLAY = {'toggle_layer', 'generate_chart'}
RE_UNPARSED = re.compile(r'(```tool_code|```tool|<tool_call>|<function|<\|python_(start|end)\|>|"(name|function)"\s*:\s*\{?\s*"?(name"\s*:\s*")?(lookup|analyze|compare|find|toggle|generate|get_|list_|query_|create_|select_|reject)|\[\s*(analysis|province lookup|municipality lookup|layer listing|lookup|chart)\s*\(|\b(lookup_province|lookup_municipality|analyze_area|analyze_multi_layer|compare_areas|find_top_n|get_legend|toggle_layer|generate_chart|list_layers|get_layer_bounds|query_erosion_stats|reject_task)\s*\(|^\s*analysis\s*\()', re.I | re.M)
RE_ANNOUNCE = re.compile(r"(i will (now )?(perform|analy[sz]e|look up|use|call|query|retrieve|check|start|first)|i'll (now )?(analy[sz]e|look up|use|call|query|retrieve|check|start|first|perform|proceed)|let me (now )?(analy[sz]e|look up|use|call|query|retrieve|check|start|first|get|pull|run)|now,? (i will|i'll|let me)|next,? (i will|i'll|let me)|to (do|answer) (this|that),? i (will|need to))", re.I)
METADATA = {'get_legend', 'get_layer_bounds', 'list_layers', 'get_layer_info'}
RE_CLARIFY = re.compile(r"(could you (please )?(clarify|specify|confirm|provide|tell)|would you like|do you want|please (clarify|specify|confirm|provide|let me know)|can you (clarify|specify|confirm)|which (one|province|municipality) (do|did) you)", re.I)
RE_REFUSE = re.compile(r"(i (can(no|')t|cannot|am unable|'m unable|don't have|do not have|am not able)|not (available|supported|covered|possible)|(outside|beyond) (the|my|of)|does not (cover|support|include|have)|doesn't (cover|support|include|have)|no data (for|on|available)|unfortunately|only (covers?|available|for|analy[sz]e|rank|supports?)|not (yet )?available|i'?m sorry)", re.I)
RE_NUM = re.compile(r'\d+(?:[.,]\d+)?\s?%')
RE_TOOLERR = re.compile(r'"error"\s*:|Error:|error_type|not found|Could not', re.I)

def tool_results(ct):
    out = []
    for t in L(ct):
        c = t.get('content') if isinstance(t, dict) else None
        if t.get('role') == 'user' and isinstance(c, str) and 'tool_result' in c: out.append(c)
        elif t.get('role') == 'user' and isinstance(c, list):
            out += [str(x) for x in c if isinstance(x, dict) and x.get('type') == 'tool_result']
        elif t.get('role') == 'tool': out.append(str(c))
    return out

def subtype(f, t, case):
    called = [x.get('tool') for x in L(t.get('tools_called'))] or L(t.get('tools_used'))
    used = set(called)
    ch = next((c for c in L(t.get('checks')) if c.get('check') == 'expected_tools'), {})
    exp = set(ch.get('expected') or case.get('expected_tools') or []); miss = set(ch.get('missing') or (exp - used))
    ans = str(t.get('full_answer') or '').strip()
    res = tool_results(t.get('conversation_trace')); errs = [r for r in res if RE_TOOLERR.search(r)]
    maxr = case.get('max_rounds') or 10
    feat = dict(n_tools=len(called), tools_called='|'.join(called), expected='|'.join(sorted(exp)),
                missing='|'.join(sorted(miss)), n_tool_errors=len(errs), answer_chars=len(ans),
                hit_round_limit=int(f['rounds'] >= maxr), max_rounds=maxr,
                question_geological=int(bool(re.search(r'geolog', t.get('question', ''), re.I))),
                answer_geological_vs_absorption=int(bool(re.search(r'geolog', ans, re.I) and re.search(r'absor', ans, re.I))),
                has_numbers=int(bool(RE_NUM.search(ans))), refusal_lang=int(bool(RE_REFUSE.search(ans))),
                clarify_lang=int(bool(RE_CLARIFY.search(ans) or ans.endswith('?'))), unparsed_call=int(bool(RE_UNPARSED.search(ans))))
    other = [c for c in L(t.get('checks')) if c.get('check') not in ('expected_tools', 'max_cost_usd')]
    feat['other_checks_all_pass'] = int(all(c.get('passed') for c in other)) if other else 0
    feat['announced_then_stopped'] = int(bool(RE_ANNOUNCE.search(ans[-300:])))
    if feat['unparsed_call']: st = 'T1_wrote_tool_call_as_text'
    elif not used:
        if len(ans) < 40: st = 'A1_empty_answer'
        elif miss and miss <= METADATA: st = 'A2_answered_metadata_from_prompt'
        elif feat['announced_then_stopped'] and not feat['clarify_lang']: st = 'A3_announced_call_then_stopped'
        elif feat['clarify_lang'] and not feat['has_numbers']: st = 'A4_asked_user_instead'
        elif feat['refusal_lang']: st = 'A5_refused_or_claimed_limit'
        elif feat['has_numbers']: st = 'A6_gave_numbers_without_tool'
        else: st = 'A7_answered_from_knowledge'
    elif 'reject_task' in used and not (used & exp): st = 'B1_called_reject_task'
    elif feat['hit_round_limit']: st = 'B2_ran_out_of_rounds'
    elif errs and not (miss <= GEO and used & ANALYSIS): st = 'B3_gave_up_after_tool_error'
    elif miss and miss <= GEO and used & ANALYSIS: st = 'C1_skipped_geocoding_step'
    elif miss & ANALYSIS and used & ANALYSIS: st = 'C2_used_a_different_analysis_tool'
    elif miss and miss <= (DISPLAY | METADATA): st = 'C3_missed_display_or_metadata_tool'
    else: st = 'C4_other_incomplete_chain'
    return st, feat

rows, tm = [], []
nomatch = 0
for f in failed:
    t = trace.get((f['model'], f['case_id'], f['seed']))
    case = cases.get(f['case_id'], {})
    row = dict(f, question=case.get('question', ''), difficulty=case.get('difficulty', ''), trace_found=int(t is not None))
    if t is None: nomatch += 1
    if f['error_category'] == 'tool_missing' and t is not None:
        st, feat = subtype(f, t, case); row.update(feat); row['subtype'] = st
        trace_agrees = int(t.get('error_category') == 'tool_missing')
        row['trace_label_agrees'] = trace_agrees
        tm.append(dict(row, answer=str(t.get('full_answer') or ''), tools_called_detail=L(t.get('tools_called')),
                       tool_results=tool_results(t.get('conversation_trace'))[:6]))
    rows.append(row)
print('no trace for', nomatch, 'failed runs')
cols = ['model','case_id','seed','category','difficulty','error_category','subtype','check_score','rounds','max_rounds',
        'hit_round_limit','n_tools','tools_called','expected','missing','n_tool_errors','answer_chars','has_numbers',
        'refusal_lang','clarify_lang','unparsed_call','announced_then_stopped','other_checks_all_pass','question_geological','answer_geological_vs_absorption',
        'trace_found','trace_label_agrees','label_source','question']
with open('data/failed_runs.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
with open('data/tool_missing_runs.jsonl', 'w') as fh:
    for r in tm: fh.write(json.dumps(r, ensure_ascii=False) + '\n')
print('tool_missing classified', len(tm)); print(collections.Counter(r['subtype'] for r in tm).most_common())
print('trace label agrees', sum(r['trace_label_agrees'] for r in tm), '/', len(tm))
