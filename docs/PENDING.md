# Pending — Gabriel's action items

Refreshed: 2026-09-03. (Previous version dated 2026-05-16 was fully stale — everything
from the submission and camera-ready phases is done.)

## Done (milestones, for the record)

- [x] SIGSPATIAL 2026: submitted June 5 → **accepted** → camera-ready (4-page short paper)
      submitted. Paper DOI: `10.1145/3841645.3844198`.
- [x] arXiv: v1 (extended 10-page preprint) June 10; **v2 = camera-ready** submitted
      2026-09-03 — `arXiv:2606.12821`. v2 is the final arXiv version.
- [x] Zenodo published (concept DOIs cited in paper, resolve to latest):
      dataset `10.5281/zenodo.20450995` (v1.3.0: 9-model leaderboard, v6 expansion,
      raw traces) · software `10.5281/zenodo.20450997` (v1.2.0: code @ `1324db9`).
- [x] Benchmark: v6 expansion run (103 tasks total); leaderboard at nine models
      (GPT-4o + Gemma-3-27B added).
- [x] MCP server exposing the 16-tool interface (`api/agent/mcp_server.py`).
- [x] `CITATION.cff`: ACM DOI + arXiv ID added; version 1.2.0.

## Open

- [ ] **Check the arXiv v2 announcement** (1–2 business days after 2026-09-03); confirm
      the public page shows the 4-page PDF, journal-ref and DOI.
- [ ] **Regenerate per-case results for all 9 models** (`results_per_case.jsonl` /
      `per_case.csv` still cover the original 7-model protocol runs only) — ship in the
      next Zenodo dataset version.
- [ ] **`api/data/spain_provinces.geojson` is 0 bytes** — municipality-level resolution
      works; check whether `lookup_province` needs the file at all, fix or drop it.
- [ ] **Stale root copy** `paper/geonatureagent_benchmark.tex` — decide: delete or mark.
- [ ] One end-to-end replicator dry run from a fresh clone (README → download_data.sh →
      docker compose → one benchmark case) to catch bit-rot.

## Nice-to-have (no deadline)

- [ ] Public landing page (GitHub Pages: leaderboard + links + how to add a model).
- [ ] Papers With Code / Hugging Face mirror for discoverability.
- [ ] Announcement thread after the SIGSPATIAL '26 proceedings go live (Nov 2026).
