# Pending — Gabriel's action items

Internal checklist. Devika-blocking decisions live in `devika_review.docx` (the email draft), not here.

Today: 2026-05-16
SIGSPATIAL 2026 abstract registration: 2026-05-22 (6 days)

---

## Before the May 22 abstract deadline

### Critical path (must happen)

- [ ] **Verify SIGSPATIAL 2026 CFP details**. Confirm on the conference website:
  - Exact deadline for May 22 — is it abstract registration only, or full paper?
  - Page limit for 2026 (current draft is 10 pages — historically the limit is 10, sometimes 9 + unlimited refs).
  - Whether the review process is double-blind. If yes, an anonymized PDF is required for submission and self-citations need to be checked (`paper/SIGSPATIAL_2026/*.tex` currently has author names visible).
  - Submission system (EasyChair? HotCRP?) and required account setup.

- [ ] **Create / log into the submission system account**. Account creation can take a day if it needs admin approval — don't leave for May 22.

- [ ] **Send the draft to Devika**. Email is in the conversation; attach `paper/SIGSPATIAL_2026/geonatureagent_benchmark.pdf` + `paper/SIGSPATIAL_2026/geonatureagent_benchmark.docx` + `HOWTOUSE.md`.

### Should happen (polish + small risk reduction)

- [ ] **Fix fig 3 legend** (`paper/generate_figures.py:fig3_binary_vs_partial`). Per-model colored bars currently show only Claude's color pair in the auto-legend. Replace with neutral handles: solid gray = binary accuracy, lighter gray = partial credit. ~5 min, doesn't affect numbers.

- [ ] **Final visual sanity-pass of the SIGSPATIAL PDF**. Open in Preview / Acrobat, skim for:
  - Layout glitches (text overflowing tables, figures bleeding past column edges)
  - Spelling and punctuation typos
  - Caption/figure-number consistency
  - Footnote rendering

- [ ] **Page-count check after Devika's edits**. If she adds material, recheck the 10-page limit.

- [x] **GitHub org: stay at `gabrielireland/`** (decided 2026-05-31). All URLs already point there — no repo transfer or URL changes needed.

### Optional (nice to have, but defer if needed)

- [ ] **Anonymization variant** of the SIGSPATIAL PDF if the venue is double-blind. Strip authors, affiliations, ORCIDs, the Darwin Geospatial acknowledgment line, the email, and any self-citations. Keep a clearly-named copy (`geonatureagent_benchmark_anon.pdf`) so it doesn't get confused with the named version post-acceptance.

---

## Before the camera-ready (post-acceptance, probably mid–late summer)

These don't block the May 22 deadline but should be done by camera-ready.

### Data hosting (Zenodo + Hugging Face)

- [ ] **Locate the two COG `.tif` files** (`co2_spain.tif`, `gully_europe.tif`). They aren't on this machine — check Cloud Run job mount, GCS bucket from the most recent paper run, or re-derive from source MITECO / JRC LUCAS data.

- [ ] **Create a Zenodo account + Personal Access Token** with `deposit:write` and `deposit:actions` scopes. Save the token securely (1Password, etc.).

- [ ] **Prepare Zenodo metadata** (title, creators with ORCIDs, description, license = Apache 2.0 for code OR CC-BY-4.0 for data, keywords, related-identifiers pointing at the GitHub repo and the SIGSPATIAL DOI once known).

- [ ] **Upload to Zenodo**. Get the dataset DOI. Add a `DATA_README.md` inside the deposit explaining file specs (projection, value ranges, source datasets, processing steps).

- [ ] **Mirror on Hugging Face Datasets** (optional but recommended for LLM-agent community discoverability). Push as a dataset with a dataset card; uses the same metadata.

- [ ] **Replace placeholder URLs in `scripts/download_data.sh`** with the actual Zenodo URLs once they exist. Currently the script exits with a manual-placement message if the env vars aren't set.

- [ ] **Add the Zenodo DOI to `paper/references.bib`** as a `@dataset{}` entry. Cite it in §3.1 (Benchmark Design) and update `Section{Online Resources}` in the SIGSPATIAL appendix to point at the DOI too.

### GitHub repo finalization

- [ ] **Repo lives at the right URL** (see "Decide the GitHub org" above — same item, just confirming).

- [ ] **Repo has a Zenodo-linked release** so the code itself gets a DOI alongside the data. Set up via Zenodo's GitHub integration: enable the toggle for the repo, cut a tagged release, the DOI registers automatically.

- [ ] **`CITATION.cff` updated** with the final DOIs (paper, code, data).

### Paper polish

- [ ] **Fix fig 3 legend** (if not already done for the abstract).

- [ ] **Final caption + figure-number audit** — make sure every figure is referenced from the body and every reference resolves.

- [ ] **References.bib audit** — anything cited as preprint that's now published gets the journal/conf entry. Anything cited as 2024/2025 placeholder that turned into 2026 gets updated.

- [ ] **Bring the arxiv version in line** with whatever camera-ready edits land in the SIGSPATIAL version. Currently both are content-aligned; keep them that way.

- [ ] **Submit the arxiv version** to arxiv once SIGSPATIAL accepts (don't post to arxiv before acceptance if the venue prohibits — check the SIGSPATIAL policy on preprints).

### Infrastructure & reproducibility

- [ ] **One end-to-end replicator dry run** from a fresh clone of the final repo: `cp .env.example .env`, set the Anthropic key, `./scripts/download_data.sh`, `docker compose up`, then `python -m geoagentbench --cases dev`. Confirm a stranger can reproduce a single case. Catch any broken paths from the repo move.

- [ ] **Update `HOWTOUSE.md`** if the data-download steps change after Zenodo is live (`CO2_SPAIN_URL` and `GULLY_EUROPE_URL` env vars will then have stable defaults).

---

## Nice-to-have (no deadline, can drift)

- [ ] **Public landing page** for the benchmark (e.g., a GitHub Pages site with the leaderboard, links to paper/data/code, instructions for adding a new model). Other benchmarks do this and it materially helps citation.

- [ ] **Submit to the Hugging Face leaderboards / Papers With Code** to surface the benchmark to the LLM-agent community after publication.

- [ ] **Tweet / Bluesky thread announcement** after SIGSPATIAL publishes.
