#!/usr/bin/env python3
"""Verify GeoAgentBench publication package consistency.

Reads from the 4 sources of truth and checks that all derived artifacts
(READMEs, figures, paper, HuggingFace dataset) are consistent.

Usage:
    python scripts/verify_package.py
    python scripts/verify_package.py --results-dir /tmp/geoagentbench_v5_results
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASES_FILE = REPO / "geoagentbench" / "cases" / "benchmark_v5.json"
PAPER_TEX = REPO / "agentic_documentation" / "paper" / "geoagentbench.tex"
REFERENCES_BIB = REPO / "agentic_documentation" / "paper" / "references.bib"
FIGURES_DIR = REPO / "agentic_documentation" / "paper" / "figures"
HF_DIR = REPO / "hf_dataset"

EXPECTED_CASES = 93
EXPECTED_CATEGORIES = 18
EXPECTED_MODELS = 8

# Paper Table 4 — accuracy per model (source of truth: results.jsonl files)
# NOTE: These are pre-rerun values (20 BigEarthNet cases all fail). Update after re-run
# with bigearthnet_lulc wired into the agent.
EXPECTED_ACCURACY = {
    "exp_035_gemini25_pro_v5": 39.8,
    "exp_036_deepseek_v32_v5": 52.7,
    "exp_037_llama4_maverick_v5": 0.0,
    "exp_038_gpt_oss_120b_v5": 39.8,
    "exp_039_glm5_v5": 58.1,
    "exp_040_qwen3_235b_v5": 47.3,
    "exp_041_llama4_scout_v5": 5.4,
    "exp_042_claude_sonnet4_v5": 58.1,
}

EXPECTED_FIGURES = [
    "fig1_leaderboard.pdf",
    "fig2_cost_accuracy.pdf",
    "fig3_binary_vs_partial.pdf",
    "fig4_category_heatmap.pdf",
    "fig5_hard_cases.pdf",
    "fig6_architecture.pdf",
    "fig7_tokens_accuracy.pdf",
    "fig8_scoring_pipeline.pdf",
]


class Checker:
    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.details: list[str] = []

    def ok(self, name: str, detail: str = ""):
        self.passed += 1
        msg = f"  PASS  {name}"
        if detail:
            msg += f" — {detail}"
        self.details.append(msg)

    def fail(self, name: str, detail: str):
        self.failed += 1
        self.details.append(f"  FAIL  {name} — {detail}")

    def skip(self, name: str, reason: str):
        self.skipped += 1
        self.details.append(f"  SKIP  {name} — {reason}")

    def check_case_count(self):
        cases = json.loads(CASES_FILE.read_text())
        n = len(cases)
        if n == EXPECTED_CASES:
            self.ok("case_count", f"{n} cases")
        else:
            self.fail("case_count", f"expected {EXPECTED_CASES}, got {n}")

    def check_category_count(self):
        cases = json.loads(CASES_FILE.read_text())
        cats = {c["category"] for c in cases}
        n = len(cats)
        if n == EXPECTED_CATEGORIES:
            self.ok("category_count", f"{n} categories")
        else:
            self.fail("category_count", f"expected {EXPECTED_CATEGORIES}, got {n}: {sorted(cats)}")

    def _valid_case_ids(self) -> set:
        """Return the set of case IDs in benchmark_v5.json (the source of truth)."""
        cases = json.loads(CASES_FILE.read_text())
        return {c["id"] for c in cases}

    def check_results_record_counts(self):
        if not self.results_dir or not self.results_dir.exists():
            self.skip("results_record_counts", f"results dir not found: {self.results_dir}")
            return
        valid_ids = self._valid_case_ids()
        files = sorted(self.results_dir.glob("*.jsonl"))
        if len(files) != EXPECTED_MODELS:
            self.fail("results_file_count", f"expected {EXPECTED_MODELS} files, got {len(files)}")
        for f in files:
            lines = [json.loads(l) for l in f.read_text().strip().splitlines() if l.strip()]
            matched = [l for l in lines if l.get("case_id") in valid_ids]
            n = len(matched)
            if n == EXPECTED_CASES:
                self.ok(f"results_{f.stem}", f"{n}/{len(lines)} records match")
            else:
                self.fail(f"results_{f.stem}", f"expected {EXPECTED_CASES} matching, got {n}/{len(lines)}")

    def check_results_accuracy(self):
        if not self.results_dir or not self.results_dir.exists():
            self.skip("results_accuracy", f"results dir not found: {self.results_dir}")
            return
        valid_ids = self._valid_case_ids()
        for exp_id, expected_acc in sorted(EXPECTED_ACCURACY.items()):
            path = self.results_dir / f"{exp_id}.jsonl"
            if not path.exists():
                self.fail(f"accuracy_{exp_id}", f"file not found")
                continue
            lines = [json.loads(l) for l in path.read_text().strip().splitlines()]
            filtered = [l for l in lines if l.get("case_id") in valid_ids]
            passed = sum(1 for l in filtered if l.get("passed"))
            acc = round(passed / len(filtered) * 100, 1)
            if abs(acc - expected_acc) < 0.05:
                self.ok(f"accuracy_{exp_id}", f"{acc}%")
            else:
                self.fail(f"accuracy_{exp_id}", f"expected {expected_acc}%, got {acc}%")

    def check_readme_no_stale_57(self):
        for name, path in [
            ("geoagentbench/README.md", REPO / "geoagentbench" / "README.md"),
            ("geoagentbench/cases/README.md", REPO / "geoagentbench" / "cases" / "README.md"),
        ]:
            if not path.exists():
                self.fail(f"stale_57_{name}", "file not found")
                continue
            text = path.read_text()
            # Look for "57" as a standalone count (not inside case IDs like V5_57 or ranges like V5_55--57)
            matches = [m for m in re.finditer(r"\b57\b", text) if not re.search(r"V5_\d*57|--57", text[max(0,m.start()-10):m.end()+3])]
            if matches:
                self.fail(f"stale_57_{name}", f"found {len(matches)} occurrences of '57'")
            else:
                self.ok(f"stale_57_{name}")

    def check_paper_no_todo(self):
        if not PAPER_TEX.exists():
            self.skip("paper_todo", "tex file not found")
            return
        text = PAPER_TEX.read_text()
        todos = [i for i, line in enumerate(text.splitlines(), 1) if "TODO" in line]
        if todos:
            self.fail("paper_todo", f"TODO found on lines: {todos}")
        else:
            self.ok("paper_todo")

    def check_citations(self):
        if not PAPER_TEX.exists() or not REFERENCES_BIB.exists():
            self.skip("citations", "tex or bib file not found")
            return
        tex = PAPER_TEX.read_text()
        bib = REFERENCES_BIB.read_text()
        cite_groups = re.findall(r"\\cite\{([^}]+)\}", tex)
        all_keys = set()
        for group in cite_groups:
            for key in group.split(","):
                all_keys.add(key.strip())
        bib_keys = set(re.findall(r"@\w+\{(\w+)", bib))
        missing = all_keys - bib_keys
        if missing:
            self.fail("citations", f"missing from bib: {sorted(missing)}")
        else:
            self.ok("citations", f"{len(all_keys)} keys, all resolved")

    def check_figures(self):
        for fig in EXPECTED_FIGURES:
            path = FIGURES_DIR / fig
            if path.exists():
                self.ok(f"figure_{fig}")
            else:
                self.fail(f"figure_{fig}", "not found")

    def check_license(self):
        path = REPO / "LICENSE"
        if path.exists():
            self.ok("LICENSE")
        else:
            self.fail("LICENSE", "not found")

    def check_citation_cff(self):
        path = REPO / "CITATION.cff"
        if path.exists():
            self.ok("CITATION.cff")
        else:
            self.fail("CITATION.cff", "not found")

    def check_hf_dataset(self):
        if not HF_DIR.exists():
            self.skip("hf_dataset", "hf_dataset/ directory not found")
            return
        tasks_path = HF_DIR / "tasks.jsonl"
        results_path = HF_DIR / "results.jsonl"
        readme_path = HF_DIR / "README.md"

        if not tasks_path.exists():
            self.fail("hf_tasks", "hf_dataset/tasks.jsonl not found")
        else:
            lines = [l for l in tasks_path.read_text().strip().splitlines() if l.strip()]
            if len(lines) == EXPECTED_CASES:
                self.ok("hf_tasks", f"{len(lines)} tasks")
            else:
                self.fail("hf_tasks", f"expected {EXPECTED_CASES}, got {len(lines)}")

        if not results_path.exists():
            self.fail("hf_results", "hf_dataset/results.jsonl not found")
        else:
            lines = [l for l in results_path.read_text().strip().splitlines() if l.strip()]
            expected = EXPECTED_CASES * EXPECTED_MODELS  # 93 * 8 = 744
            if len(lines) == expected:
                self.ok("hf_results", f"{len(lines)} results")
            else:
                self.fail("hf_results", f"expected {expected}, got {len(lines)}")

        if not readme_path.exists():
            self.fail("hf_readme", "hf_dataset/README.md not found")
        else:
            self.ok("hf_readme")

    def run_all(self):
        self.check_case_count()
        self.check_category_count()
        self.check_results_record_counts()
        self.check_results_accuracy()
        self.check_readme_no_stale_57()
        self.check_paper_no_todo()
        self.check_citations()
        self.check_figures()
        self.check_license()
        self.check_citation_cff()
        self.check_hf_dataset()

    def report(self) -> int:
        print("=" * 60)
        print("GeoAgentBench Publication Package Verification")
        print("=" * 60)
        for line in self.details:
            print(line)
        print("-" * 60)
        total = self.passed + self.failed + self.skipped
        print(f"  {self.passed} passed, {self.failed} failed, {self.skipped} skipped ({total} checks)")
        if self.failed:
            print("\n  PACKAGE NOT READY — fix failures above")
            return 1
        elif self.skipped:
            print("\n  PACKAGE OK (with skips)")
            return 0
        else:
            print("\n  ALL CHECKS PASSED")
            return 0


def main():
    parser = argparse.ArgumentParser(description="Verify GeoAgentBench publication package")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("/tmp/geoagentbench_v5_results"),
        help="Directory containing per-model results.jsonl files",
    )
    args = parser.parse_args()

    checker = Checker(results_dir=args.results_dir)
    checker.run_all()
    sys.exit(checker.report())


if __name__ == "__main__":
    main()
