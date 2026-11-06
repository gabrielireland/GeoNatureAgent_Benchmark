"""Manual, evidence-based root cause per task for the 38 tasks that hold 75% of tool-missing runs.
Harness failures (call written as text, empty answer/timeout) and wording refusals stay run-level.
Runs on all other tasks keep the rule-based verdict from 08_root_cause.py."""
import csv, json, collections
EVID = {
 'P1': ('US', 'Prompt supplies the answer and discourages the tool',
        'v3.md L11 "KNOWN DATA (use this instead of calling list_layers or get_legend when possible)"; L263 conceptual questions "Do NOT call any tools"; L264 "Do NOT call list_layers or get_legend first"; L265 "Only call list_layers if the user asks about data you don\'t recognize above"'),
 'P2': ('US', 'Prompt states the answer and says to reject',
        'v3.md L44 "Las Palmas and Santa Cruz de Tenerife have no erosion data"; L239 reject_task "use when ... outside Europe (for erosion)"'),
 'P3': ('US', 'Prompt mandates a different route than the task expects',
        'v3.md L151 "MANDATORY ... you MUST call compare_areas" / L180 "use instead of separate lookup_province + analyze_area"; L276 "Single province + both indicators: use analyze_multi_layer" (takes the province name; no lookup needed) vs. L128 "just call analyze_area for each layer"'),
 'G1': ('US', 'Ground truth or expected tool is wrong',
        'V5_47: task note "No NDVI layer exists", but tool query_erosion_stats serves NDVI for Murcia municipalities. V5_73/V5_85: expect analyze_multi_layer at municipality level, but its only area parameter is `province`'),
 'W1': ('US', 'Task wording: "geological storage" vs. an absorption layer',
        'Question says CO2 "geological storage"; v3.md L15 and the layer describe CO2 absorption (reforestation) projects, so agents decline'),
 'S1': ('SHARED', 'Prompt silent; the answer is already in context',
        'get_layer_bounds is never mentioned in v3.md, but coverage is in KNOWN DATA (L13, L21, L31, L44); agents answer without verifying'),
 'S2': ('SHARED', 'Task not feasible as specified within the round budget',
        'Ranking all municipalities of a province (Málaga ~100, Murcia 45) needs 2 calls each; max_rounds = 12 and there is no municipality ranking tool for these metrics'),
 'A1': ('AGENT', 'Skipped a tool the prompt mandates',
        'v3.md L42-43 "use find_top_n ... always call find_top_n" (find_top_n has filter_provinces); L168 display-only quantitative questions "ALWAYS toggle the requested layer ON"; L276 analyze_multi_layer for province deep dives; L36 BigEarthNet "Call lookup_province ... then analyze_area"'),
}
TASK = {**{k: 'P1' for k in ['V5_61_list_layers_analyzable','V5_76_legend_ines_erosion_visual','V5_77_legend_mfe_forest_map','V5_78_legend_two_layers_compare','V5_58_legend_co2_classes','V5_59_legend_erosion_scale','V5_79_list_layers_display_only','V5_81_list_layers_unavailable_indicator','V5_74_deep_dive_temporal_profile','V5_80_list_layers_before_workflow']},
        'V5_12_spatial_island_limitations': 'P2',
        **{k: 'P3' for k in ['V5_25_tool_selection_chart_type','V5_72_interpretation_erosion_project_risk','V5_70_interpretation_investor','V5_23_deep_dive_full_profile','V5_92_deep_dive_two_provinces_side_by_side']},
        **{k: 'G1' for k in ['V5_47_error_recovery_fallback_indicator','V5_85_multi_layer_municipality_lorca','V5_73_deep_dive_municipality']},
        **{k: 'W1' for k in ['V5_11_spatial_autonomous_community','V5_21_comparison_close_values','V5_01_municipality_co2_lorca','V5_30_single_analysis_co2']},
        **{k: 'S1' for k in ['V5_66_layer_bounds_cross_border','V5_84_layer_bounds_coverage_comparison','V5_65_layer_bounds_erosion_extent','V5_83_layer_bounds_balearic_erosion','V5_64_layer_bounds_canary_co2']},
        **{k: 'S2' for k in ['V5_41_multi_muni_ranking_erosion','V5_42_multi_muni_ranking_co2']},
        **{k: 'A1' for k in ['V5_45_province_aggregation_aragon','V5_44_province_aggregation_andalucia','V5_75_deep_dive_community_ranking','V5_17_error_ines_stats_fabrication','V5_68_multi_layer_nbs_profile','V5_93_deep_dive_national_policy_brief','V5_62_list_layers_habitat_years','V5_90_interpretation_bank_risk_assessment']}}
RULE2CODE = {'US (prompt discouraged the tool)': 'P1', 'US (prompt recommended another route)': 'P3', 'US (task wording)': 'W1',
             'SHARED (prompt silent; answer in context)': 'S1', 'AGENT (skipped a tool the prompt mandates)': 'A1', 'AGENT (other)': 'A1'}
rows = list(csv.DictReader(open('tables/14_root_cause_by_run.csv')))
TMJ = {(r['model'], r['case_id'], r['seed']): r for r in map(json.loads, open('data/tool_missing_runs.jsonl'))}
out = []
for r in rows:
    t = TMJ[(r['model'], r['case_id'], r['seed'])]
    if r['verdict'] == 'US (harness)':
        code = 'H1' if r['subtype'].startswith('T1') else 'H2'
    elif r['verdict'] == 'US (task wording)':
        code = 'W1'
    elif r['case_id'] in TASK:
        code = TASK[r['case_id']]
    else:
        code = RULE2CODE[r['verdict']]
    if 'list_layers' in r['tools_called'] and any(s in t['question'] for s in ['BigEarthNet','Portugal','Beja','Faro','Lisboa','Portalegre','Setubal','Setúbal']):
        code = 'T2'
    out.append(dict(r, code=code, basis='task-level review' if r['case_id'] in TASK else 'rule'))
EVID['H1'] = ('US', 'Harness did not execute a tool call written as text', 'Gemma ```tool_code / JSON call arrays; Llama [analysis(...)] with <|python_start|>; universal parser misses these dialects')
EVID['H2'] = ('US', 'Infrastructure: timeout or provider error', 'error field "Case timed out after 300s" (36), litellm InternalServerError (5), API 400 (1)')
EVID['T2'] = ('US', 'Tool bug: list_layers omits BigEarthNet', 'Real list_layers output lists only co2_spain_legislation and rf_gully_probability; agents that checked were told the Portugal layer does not exist')
with open('tables/16_root_cause_final.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
C = collections.Counter(r['code'] for r in out); G = collections.Counter(EVID[r['code']][0] for r in out)
summ = [[k, EVID[k][0], EVID[k][1], C[k], round(100*C[k]/len(out),1), sum(1 for r in out if r['code']==k and r['other_checks_all_pass']=='1'), EVID[k][2]] for k in sorted(C, key=lambda k: (['US','SHARED','AGENT'].index(EVID[k][0]), -C[k]))]
with open('tables/17_root_cause_summary.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['code','who','cause','runs','pct_of_tool_missing','otherwise_correct','evidence']); w.writerows(summ)
for s in summ: print(f'{s[0]} {s[1]:6s} {s[3]:4d} {s[4]:5.1f}%  ok={s[5]:3d}  {s[2]}')
print({g: f'{n} ({100*n/len(out):.1f}%)' for g, n in G.items()}, 'task-level share', sum(r['basis']=='task-level review' for r in out))
MODELS = ['Claude Sonnet 4','DeepSeek V3.2','GLM-5','Gemini 2.5 Pro','GPT-4o','Qwen3-235B','GPT-OSS-120B','Llama 4 Scout','Gemma-3-27B']
pm = collections.Counter((r['model'], EVID[r['code']][0]) for r in out)
with open('tables/18_who_by_model.csv','w',newline='') as fh:
    w = csv.writer(fh); w.writerow(['model','US','SHARED','AGENT','tool_missing'])
    for m in MODELS: w.writerow([m, pm[(m,'US')], pm[(m,'SHARED')], pm[(m,'AGENT')], sum(pm[(m,g)] for g in ('US','SHARED','AGENT'))])
print(open('tables/18_who_by_model.csv').read()); json.dump(EVID, open('tables/root_cause_evidence.json','w'), indent=1, ensure_ascii=False)
