"""Match each leaderboard model to the raw-trace run that reproduces the published per-case results."""
import json, glob, os, collections
T = os.environ.get('GNA_RAW_TRACES', os.path.expanduser('~/geonature_raw_traces/GeoNatureAgent/experiments'))  # raw agent traces, not in git
P = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))  # repo root
pub = [json.loads(l) for l in open(f'{P}/hf_dataset/results.jsonl')]
PUB = collections.defaultdict(dict)
for r in pub: PUB[r['experiment_id']][(r['case_id'], str(r['seed']))] = (str(r['passed']), round(float(r['check_score']), 3))
cands = {e: glob.glob(f'{T}/*/{e}/results.jsonl') for e in PUB}
out = {}
for e, files in cands.items():
    best = None
    for f in files:
        R = [json.loads(l) for l in open(f)]
        k = {(r['case_id'], str(r.get('seed'))): (str(r['passed']), round(float(r['check_score']), 3)) for r in R}
        ref = PUB[e]; common = set(k) & set(ref)
        agree = sum(k[x] == ref[x] for x in common)
        sc = (agree, len(common))
        print(f'{e}  {os.path.basename(os.path.dirname(os.path.dirname(f)))}  rows={len(R)} common={len(common)} agree={agree}/{len(ref)}')
        if best is None or sc > best[0]: best = (sc, f)
    out[e] = best[1]
# GPT-4o and Gemma-3 are not in hf_dataset/results.jsonl; use the leaderboard runs kept in the public repo.
out['gpt4o_openrouter_v5'] = f'{P}/results/run_gpt4o_openrouter_v5/results.jsonl'
out['gemma3_openrouter_v5'] = f'{P}/results/run_gemma3_openrouter_v5/results.jsonl'
json.dump(out, open('data/selected_runs.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
