import csv; import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib.colors import LinearSegmentedColormap
T = list(csv.DictReader(open('tables/03_subtype_by_model.csv'))); M = [k for k in T[0] if k != 'subtype']
RUNS = {m: (186 if m == 'Claude Sonnet 4' else 279) for m in M}
order = [r['subtype'] for r in csv.DictReader(open('tables/01_subtypes.csv'))]; T = sorted(T, key=lambda r: order.index(r['subtype']))
Z = [[100*int(r[m])/RUNS[m] for m in M] for r in T]
cmap = LinearSegmentedColormap.from_list('b', ['#fcfcfb', '#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b'])
fig, ax = plt.subplots(figsize=(11, 7.2), dpi=200); fig.patch.set_facecolor('#fcfcfb')
im = ax.imshow(Z, cmap=cmap, vmin=0, vmax=36, aspect='auto')
for i, row in enumerate(Z):
    for j, v in enumerate(row):
        if v >= 0.5: ax.text(j, i, f'{v:.0f}' if v >= 1 else '<1', ha='center', va='center', fontsize=8, color='white' if v > 14 else '#0b0b0b')
ax.set_xticks(range(len(M))); ax.set_xticklabels(M, rotation=30, ha='right', fontsize=9)
ax.set_yticks(range(len(T))); ax.set_yticklabels([r['subtype'].split('_',1)[0] + '  ' + r['subtype'].split('_',1)[1].replace('_',' ') for r in T], fontsize=8.5)
ax.set_xticks([x-.5 for x in range(1, len(M))], minor=True); ax.set_yticks([y-.5 for y in range(1, len(T))], minor=True)
ax.grid(which='minor', color='#fcfcfb', linewidth=2); ax.tick_params(which='both', length=0)
for s in ax.spines.values(): s.set_visible(False)
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02); cb.set_label('% of the model’s runs', fontsize=8.5); cb.outline.set_visible(False); cb.ax.tick_params(labelsize=8)
ax.set_title('Tool-missing sub-types per model (% of that model’s runs)', loc='left', fontsize=12.5, fontweight='bold', pad=12)
plt.tight_layout(); plt.savefig('figures/subtype_heatmap.png', facecolor=fig.get_facecolor()); print('ok')
