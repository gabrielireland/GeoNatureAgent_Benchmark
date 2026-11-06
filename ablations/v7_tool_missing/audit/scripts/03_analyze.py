"""Tables, sensitivity analysis and figure for the tool_missing breakdown."""
import csv, json, collections, os, re
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
P = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))  # repo root
F = list(csv.DictReader(open('data/failed_runs.csv')))
TM = [r for r in F if r['error_category'] == 'tool_missing']
MODELS = ['Claude Sonnet 4','DeepSeek V3.2','GLM-5','Gemini 2.5 Pro','GPT-4o','Qwen3-235B','GPT-OSS-120B','Llama 4 Scout','Gemma-3-27B']
RUNS = {m: (186 if m == 'Claude Sonnet 4' else 279) for m in MODELS}
FAMILY = {
 'A2_answered_metadata_from_prompt': '1 Answer already in the prompt (metadata tasks)',
 'T1_wrote_tool_call_as_text': '2 Harness / format (call not executed)', 'A1_empty_answer': '2 Harness / format (call not executed)',
 'A3_announced_call_then_stopped': '3 Agent chose not to act', 'A4_asked_user_instead': '3 Agent chose not to act',
 'A5_refused_or_claimed_limit': '3 Agent chose not to act', 'A6_gave_numbers_without_tool': '3 Agent chose not to act',
 'A7_answered_from_knowledge': '3 Agent chose not to act', 'B1_called_reject_task': '3 Agent chose not to act',
 'B2_ran_out_of_rounds': '4 Chain broke or took another route', 'B3_gave_up_after_tool_error': '4 Chain broke or took another route',
 'C1_skipped_geocoding_step': '4 Chain broke or took another route', 'C2_used_a_different_analysis_tool': '4 Chain broke or took another route',
 'C3_missed_display_or_metadata_tool': '4 Chain broke or took another route', 'C4_other_incomplete_chain': '4 Chain broke or took another route'}
for r in TM: r['family'] = FAMILY[r['subtype']]
FAMS = sorted(set(FAMILY.values())); SUBS = sorted(FAMILY)

def write(name, header, rows):
    with open(f'tables/{name}', 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(rows)

# 1. subtype totals
c = collections.Counter(r['subtype'] for r in TM); ok = collections.Counter(r['subtype'] for r in TM if r['other_checks_all_pass'] == '1')
write('01_subtypes.csv', ['family','subtype','runs','pct_of_tool_missing','pct_of_all_failures','other_checks_all_pass'],
      [[FAMILY[s], s, c[s], round(100*c[s]/len(TM),1), round(100*c[s]/len(F),1), ok[s]] for s in sorted(SUBS, key=lambda s: (FAMILY[s], -c[s]))])
# 2. family x model
fm = collections.Counter((r['model'], r['family']) for r in TM); tmm = collections.Counter(r['model'] for r in TM)
write('02_family_by_model.csv', ['model','runs','tool_missing']+FAMS, [[m, RUNS[m], tmm[m]]+[fm[(m,f)] for f in FAMS] for m in MODELS])
# 3. subtype x model
sm = collections.Counter((r['model'], r['subtype']) for r in TM)
write('03_subtype_by_model.csv', ['subtype']+MODELS, [[s]+[sm[(m,s)] for m in MODELS] for s in SUBS])
# 4. family x category
fc = collections.Counter((r['category'], r['family']) for r in TM); cats = sorted({r['category'] for r in TM}, key=lambda k: -sum(fc[(k,f)] for f in FAMS))
write('04_family_by_category.csv', ['category','tool_missing']+FAMS, [[k, sum(fc[(k,f)] for f in FAMS)]+[fc[(k,f)] for f in FAMS] for k in cats])
# 5. which expected tools are missing
mt = collections.Counter(t for r in TM for t in r['missing'].split('|') if t)
write('05_missing_tool_counts.csv', ['tool','runs_where_missing'], mt.most_common())
# 6. cases
cc = collections.Counter(r['case_id'] for r in TM); cs = collections.defaultdict(collections.Counter)
for r in TM: cs[r['case_id']][r['subtype']] += 1
q = {r['case_id']: r['question'] for r in TM}
write('06_top_cases.csv', ['case_id','tool_missing_runs_of_27','dominant_subtype','question'],
      [[k, n, cs[k].most_common(1)[0][0], q[k]] for k, n in cc.most_common(25)])
# 7. sensitivity: accuracy if runs whose ONLY failing check is expected_tools were counted as passes
pc = list(csv.DictReader(open(f'{P}/paper/final_results/per_case.csv')))
lb = {r['model']: float(r['accuracy_mean']) for r in csv.DictReader(open(f'{P}/paper/final_results/leaderboard.csv'))}
sens = []
for m in MODELS:
    a = sum(1 for r in TM if r['model'] == m and r['other_checks_all_pass'] == '1' and r['subtype'] == 'A2_answered_metadata_from_prompt')
    b = sum(1 for r in TM if r['model'] == m and r['other_checks_all_pass'] == '1')
    n = RUNS[m]; base = lb[m]
    sens.append([m, round(100*base,1), round(100*(base + a/n),1), round(100*(base + b/n),1), a, b])
order = lambda col: [r[0] for r in sorted(sens, key=lambda r: -r[col])]
write('07_sensitivity_accuracy.csv', ['model','published_strict_acc','acc_if_metadata_from_prompt_counted','acc_if_any_tool_only_fail_counted','n_metadata_flip','n_any_flip'], sens)
# 8. geological wording
v5 = json.load(open(f'{P}/geoagentbench/cases/benchmark_v5.json')); v5 = v5['cases'] if isinstance(v5, dict) else v5
geo_cases = {c['id'] for c in v5 if re.search(r'geolog', c['question'], re.I)}
allruns = [r for r in pc] ; 
def rate(ids, rows): x=[r for r in rows if r['case_id'] in ids]; return len(x), sum(r['passed']=='1' for r in x)
g_n, g_p = rate(geo_cases, pc); o_n, o_p = rate({c['id'] for c in v5} - geo_cases, pc)
geo_tm = [r for r in TM if r['case_id'] in geo_cases]; geo_refuse = [r for r in TM if r['answer_geological_vs_absorption'] == '1']
fails_geo = [r for r in F if r['case_id'] in geo_cases]
write('08_geological_wording.csv', ['metric','value'], [
 ['v5 cases whose question says "geological"', len(geo_cases)], ['case ids', ' '.join(sorted(geo_cases))],
 ['pass rate on those cases (7 models, per_case.csv)', f'{100*g_p/g_n:.1f}% of {g_n}'],
 ['pass rate on all other cases (7 models)', f'{100*o_p/o_n:.1f}% of {o_n}'],
 ['failed runs on those cases (9 models)', len(fails_geo)], ['  of which tool_missing', len(geo_tm)],
 ['tool_missing runs whose answer contrasts geological vs absorption', len(geo_refuse)]])
json.dump({'n_failed': len(F), 'n_tool_missing': len(TM), 'geo_cases': sorted(geo_cases),
           'rank_published': order(1), 'rank_metadata': order(2), 'rank_any': order(3)}, open('tables/summary.json', 'w'), indent=1)

# ---- figure: tool_missing families per model (share of that model's runs) ----
COL = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']   # validated: reference categorical slots 1-4 (light)
fig, ax = plt.subplots(figsize=(11, 5.6), dpi=200); fig.patch.set_facecolor('#fcfcfb'); ax.set_facecolor('#fcfcfb')
ys = range(len(MODELS))[::-1]
for y, m in zip(ys, MODELS):
    left = 0
    for i, f in enumerate(FAMS):
        v = 100 * fm[(m, f)] / RUNS[m]
        if v <= 0: continue
        ax.barh(y, v - 0.3, left=left, color=COL[i], height=0.62, edgecolor='none')
        if v >= 3.2: ax.text(left + v/2, y, f'{v:.0f}', ha='center', va='center', fontsize=8.5, color='#0b0b0b' if i in (2, 3) else 'white', fontweight='bold')
        left += v
    ax.text(left + 0.8, y, f'{100*tmm[m]/RUNS[m]:.0f}% of runs', va='center', fontsize=8.5, color='#52514e')
ax.set_yticks(list(ys)); ax.set_yticklabels(MODELS, fontsize=9.5, color='#0b0b0b')
ax.set_xlabel('“Tool missing” failures, % of the model’s runs (main suite, 93 tasks × seeds)', fontsize=9, color='#52514e')
for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
ax.spines['bottom'].set_color('#c9c8c2'); ax.tick_params(axis='x', colors='#52514e', labelsize=8.5); ax.tick_params(axis='y', length=0)
ax.grid(axis='x', color='#e8e7e3', linewidth=0.8); ax.set_axisbelow(True); ax.set_xlim(0, 80)
h = [plt.Rectangle((0, 0), 1, 1, color=COL[i]) for i in range(4)]
ax.legend(h, [f[2:] for f in FAMS], loc='lower center', bbox_to_anchor=(0.45, 1.0), ncol=2, frameon=False, fontsize=9)
ax.set_title('Why the expected tool was never called', loc='left', fontsize=12.5, fontweight='bold', color='#0b0b0b', pad=38)
plt.tight_layout(); plt.savefig('figures/tool_missing_families_by_model.png', facecolor=fig.get_facecolor()); print('figure ok')
for f in sorted(os.listdir('tables')): print('table', f)
