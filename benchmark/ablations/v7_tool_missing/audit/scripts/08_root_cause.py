"""Root-cause attribution: for each tool_missing run, did OUR prompt/harness steer the agent away from the
expected tool (US), did the prompt mandate it and the agent skipped it (AGENT), or was the prompt silent (SHARED)?
Prompt stance per tool is read from api/agent/prompts/v3.md (line numbers cited in the casebook)."""
import json, csv, collections, ast, os, re
TM = [json.loads(l) for l in open('data/tool_missing_runs.jsonl')]
L = lambda x: x if isinstance(x, list) else (ast.literal_eval(x) if x else [])
DISCOURAGED = {'get_legend': 'L11, L263-265: "use KNOWN DATA instead of calling list_layers or get_legend"; "Do NOT call list_layers or get_legend first"; conceptual questions: "Do NOT call any tools"',
               'list_layers': 'L11, L264-265: "Do NOT call list_layers or get_legend first"; "Only call list_layers if the user asks about data you don\'t recognize above"'}
MANDATED = {'find_top_n': 'L43: "always call find_top_n"', 'compare_areas': 'L151: "MANDATORY ... you MUST call compare_areas"',
            'generate_chart': 'L189/L208/L244: "ALWAYS call generate_chart" / "MANDATORY"', 'lookup_province': 'L132: "first call lookup_province ... then call analyze_area"',
            'lookup_municipality': 'L138/L144: lookup_municipality for named municipalities', 'analyze_area': 'L126: standard workflow step 2',
            'create_buffer': 'L213: "MUST follow this exact two-step sequence"', 'select_features_by_spatial_relationship': 'L216/L222: "MUST call"',
            'toggle_layer': 'L168: display-only quantitative questions: "ALWAYS toggle the requested layer ON"', 'analyze_multi_layer': 'L276: "Single province + both indicators: use analyze_multi_layer"'}
SILENT = {'get_layer_bounds', 'get_layer_info', 'query_erosion_stats'}
def alt_route(miss, used):
    """Prompt-sanctioned alternative routes that make an expected tool unnecessary."""
    why = []
    if miss & {'lookup_province', 'analyze_area'} and 'analyze_multi_layer' in used: why.append('L276 recommends analyze_multi_layer for one province + both layers (no lookup needed)')
    if 'analyze_multi_layer' in miss and 'analyze_area' in used: why.append('L128: "For combined carbon + erosion analysis, just call analyze_area for each layer"')
    if miss & {'lookup_province', 'analyze_area'} and 'compare_areas' in used: why.append('L180: compare_areas "use instead of separate lookup_province + analyze_area"')
    return why
rows = []
for r in TM:
    used = set(t for t in r['tools_called'].split('|') if t); miss = set(t for t in r['missing'].split('|') if t)
    if r['subtype'] in ('T1_wrote_tool_call_as_text', 'A1_empty_answer'):
        v, why = 'US (harness)', 'tool call written as text not parsed' if r['subtype'].startswith('T1') else 'empty answer (timeout / provider error)'
    elif r.get('answer_geological_vs_absorption') == 1 and r.get('question_geological') == 1:
        v, why = 'US (task wording)', 'question says CO2 "geological storage"; prompt L15 and the layer describe CO2 absorption projects, so the agent refused'
    elif miss and miss <= set(DISCOURAGED):
        v, why = 'US (prompt discouraged the tool)', '; '.join(DISCOURAGED[t] for t in sorted(miss))
    elif alt_route(miss, used) and not (miss - {'lookup_province', 'analyze_area', 'analyze_multi_layer', 'lookup_municipality'}):
        v, why = 'US (prompt recommended another route)', '; '.join(alt_route(miss, used))
    elif miss & set(MANDATED) - (set(DISCOURAGED)):
        mand = sorted(miss & set(MANDATED)); v, why = 'AGENT (skipped a tool the prompt mandates)', '; '.join(f'{t}: {MANDATED[t]}' for t in mand)
    elif miss <= SILENT | set(DISCOURAGED):
        v, why = 'SHARED (prompt silent; answer in context)', 'prompt never mentions ' + ', '.join(sorted(miss & SILENT))
    else:
        v, why = 'AGENT (other)', ''
    rows.append(dict(model=r['model'], case_id=r['case_id'], seed=r['seed'], category=r['category'], subtype=r['subtype'], verdict=v,
                     reason=why, tools_called=r['tools_called'], missing=r['missing'], other_checks_all_pass=r['other_checks_all_pass']))
with open('tables/14_root_cause_by_run.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
V = collections.Counter(r['verdict'] for r in rows); print(len(rows)); [print(f'{n:4d} {100*n/len(rows):5.1f}%  {k}') for k, n in V.most_common()]
ok = collections.Counter(r['verdict'] for r in rows if r['other_checks_all_pass'] == 1); print('otherwise correct by verdict', dict(ok))
# who: US vs AGENT vs SHARED per model
MODELS = ['Claude Sonnet 4','DeepSeek V3.2','GLM-5','Gemini 2.5 Pro','GPT-4o','Qwen3-235B','GPT-OSS-120B','Llama 4 Scout','Gemma-3-27B']
grp = lambda v: v.split(' ')[0]
pm = collections.Counter((r['model'], grp(r['verdict'])) for r in rows)
with open('tables/15_root_cause_by_model.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['model', 'US', 'SHARED', 'AGENT', 'total'])
    for m in MODELS: w.writerow([m, pm[(m,'US')], pm[(m,'SHARED')], pm[(m,'AGENT')], sum(pm[(m,g)] for g in ('US','SHARED','AGENT'))])
print(open('tables/15_root_cause_by_model.csv').read())
# agent-mandated breakdown: which mandated tool skipped + what the agent did instead
am = [r for r in rows if r['verdict'].startswith('AGENT (skipped')]
print('mandated tool skipped:', collections.Counter(t for r in am for t in r['missing'].split('|') if t in MANDATED).most_common())
print('their subtypes:', collections.Counter(r['subtype'] for r in am).most_common())
