"""Sensitivity dot plot + stratified audit sample for human verification."""
import csv, json, random, collections
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
S = list(csv.DictReader(open('tables/07_sensitivity_accuracy.csv')))
fig, ax = plt.subplots(figsize=(10, 5.2), dpi=200); fig.patch.set_facecolor('#fcfcfb'); ax.set_facecolor('#fcfcfb')
B, O = '#2a78d6', '#eb6834'
for y, r in zip(range(len(S))[::-1], S):
    a, b = float(r['published_strict_acc']), float(r['acc_if_metadata_from_prompt_counted'])
    ax.plot([a, b], [y, y], color='#c9c8c2', linewidth=2, zorder=1)
    ax.scatter([a], [y], s=70, color=B, zorder=3, edgecolors='#fcfcfb', linewidths=2)
    ax.scatter([b], [y], s=70, color=O, zorder=3, edgecolors='#fcfcfb', linewidths=2)
    ax.text(a - 1.2, y, f'{a:.1f}', ha='right', va='center', fontsize=8.5, color='#52514e')
    ax.text(b + 1.2, y, f'{b:.1f}  (+{b-a:.1f})', ha='left', va='center', fontsize=8.5, color='#52514e')
ax.set_yticks(range(len(S))[::-1]); ax.set_yticklabels([r['model'] for r in S], fontsize=9.5)
ax.set_xlim(0, 85); ax.set_xlabel('Strict accuracy, main suite (%)', fontsize=9, color='#52514e')
for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
ax.spines['bottom'].set_color('#c9c8c2'); ax.tick_params(axis='y', length=0); ax.tick_params(axis='x', colors='#52514e', labelsize=8.5)
ax.grid(axis='x', color='#e8e7e3', linewidth=0.8); ax.set_axisbelow(True)
h = [plt.Line2D([], [], marker='o', linestyle='', color=c, markersize=8) for c in (B, O)]
ax.legend(h, ['Published', 'If correct metadata answers without the metadata tool counted as passes'], loc='lower center', bbox_to_anchor=(0.45, 1.0), ncol=2, frameon=False, fontsize=8.5)
ax.set_title('Sensitivity: metadata answers taken from the prompt', loc='left', fontsize=12.5, fontweight='bold', pad=30)
plt.tight_layout(); plt.savefig('figures/sensitivity_metadata_conflict.png', facecolor=fig.get_facecolor())
# stratified audit sample: 5 per subtype
R = [json.loads(l) for l in open('data/tool_missing_runs.jsonl')]; random.seed(2026)
by = collections.defaultdict(list)
for r in R: by[r['subtype']].append(r)
with open('data/audit_sample.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['subtype','model','case_id','seed','tools_called','missing','question','answer_first_400','reviewer_agrees_Y_N','reviewer_note'])
    for st in sorted(by):
        for r in random.sample(by[st], min(5, len(by[st]))):
            w.writerow([st, r['model'], r['case_id'], r['seed'], r['tools_called'], r['missing'], r['question'], r['answer'][:400].replace('\n', ' '), '', ''])
print('ok', sum(min(5, len(v)) for v in by.values()), 'audit rows')
