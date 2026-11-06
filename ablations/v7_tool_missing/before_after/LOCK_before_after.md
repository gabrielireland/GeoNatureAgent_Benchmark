# Pre-registered decision criteria — written BEFORE the "before" run (2026-11-03 17:15 PST)

Question: did the prompt/tool/task problems cause the "tool missing" failures, rather than the agent?

Design: same agent (Claude Code, claude-opus-5-5, default settings), same local MCP harness, same unmodified
scorer (geoagentbench/scoring.py at 6576859), one run each, all 103 tasks.
- BEFORE: code at commit 6576859 (+ only the MCP lookup->analyze_area injection, needed for MCP at all),
  prompt v3.md, tasks benchmark_v5.json + benchmark_v6_expansion.json.
- AFTER: working tree v7 (fixed tools, prompt v4.md, benchmark_v7.json) — already run (results_v7/).

We will say the problems were the cause ("demonstrated") only if ALL hold:
1. tool_missing failures BEFORE >= 3x AFTER, and BEFORE >= 15 runs.
2. On the 17 metadata tasks (get_legend / list_layers / get_layer_bounds), the expected metadata tool is
   called in <= 50% of BEFORE runs vs >= 90% of AFTER runs (AFTER: 17/17 already observed).
3. Most BEFORE tool_missing runs on metadata tasks pass every other check (answer correct from the prompt).

If 1 holds but 2 or 3 does not: "partly". If 1 fails: "not demonstrated"; we report that.
Caveats fixed in advance: one run, one model (same family as the author of the fixes); AFTER includes
3 task changes made after seeing AFTER results (V5_70, V5_72, V6_07), reported separately.

---
# RESULT (appended after the run, 2026-11-03 17:24 PST); criteria above unchanged

Same agent claude-opus-5-5, 103 tasks each. Capability pass: BEFORE 51, AFTER 57 (58 after the 3 post-hoc task changes).
1. tool_missing: BEFORE 23, AFTER 3 (0 after post-hoc changes); ratio 7.7x, BEFORE >= 15 → **PASS**
2. Metadata tool called on the 17 metadata tasks: BEFORE 10/17 (59%), AFTER 17/17 → **FAIL** (threshold <= 50%)
3. BEFORE metadata tool_missing runs passing every other check: 6/7 → **PASS**

**Verdict by the locked rule: PARTLY.** The fixed causes account for the drop in tool_missing for the same
model (23 → 3; every one of the 23 BEFORE tasks is one of the identified causes: wording, metadata prompt,
routes, invalid tasks, feasibility, Las Palmas, V6_07). But under the v3 prompt this model still called the
metadata tool in 59% of metadata runs, so the prompt's suppression of metadata calls is weaker for this
model than in the published runs (8–33% for the published models).
Raw files: results_before/, results_v7/ (results_before_decision1.jsonl = AFTER before post-hoc changes).
