"""Test GNA v7 before committing: Claude Code as the agent, GNA tools over MCP, prompt v4, tasks v7.
Scored with the UNMODIFIED public scorer (geoagentbench/scoring.py), capability rule (cost excused).
Post-publication ablation (see ../README.md); not part of the benchmark harness.

    python3 run_v7_test.py --out results_v7 [--ids ...] [--workers 4]
"""
import argparse, dataclasses, json, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # repo root
sys.path.insert(0, str(REPO))
from geoagentbench.case_loader import load_cases          # noqa: E402
from geoagentbench.scoring import score_result            # noqa: E402

CASES = REPO / "geoagentbench/cases/benchmark_v7.json"
PROMPT = (REPO / "api/agent/prompts/v4.md").read_text(encoding="utf-8")
SERVER = REPO / "api/agent/mcp_server.py"


def history_text(h):
    out = []
    for turn in h or []:
        c = turn.get("content")
        if isinstance(c, list):
            c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
        if c:
            out.append(f"{turn.get('role', 'user').capitalize()}: {c}")
    return "\n".join(out)


def derive_actions_and_charts(calls):
    """Map actions as the FastAPI agent loop emits them (successful lookups -> boundary + fly_to_bounds)
    and chart URLs from generate_chart results."""
    actions, charts = [], []
    for tool, raw in calls:
        try:
            res = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if tool in ("lookup_province", "lookup_municipality") and res.get("found"):
            if res.get("country") != "Portugal":
                actions.append({"type": "show_province_boundary"})
            actions.append({"type": "fly_to_bounds"})
        if tool == "generate_chart" and (res.get("gcs_uri") or res.get("url")):
            charts.append(res.get("gcs_uri") or res.get("url"))
    return actions, charts


def capability_passed(checks):
    gate = [c for c in checks if not str(c.get("check", "")).startswith("cost")]
    return bool(checks) and all(c.get("passed") for c in gate)


def run_case(case, timeout, prompt=None, server=None):
    prompt = prompt or PROMPT; server = server or SERVER
    q = case["question"]
    if case.get("session_history"):
        q = f"Earlier in this conversation:\n{history_text(case['session_history'])}\n\nNow the user says: {q}"
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"gna": {"command": sys.executable, "args": [str(server)]}}}))
        cmd = ["claude", "-p", q, "--output-format", "stream-json", "--verbose", "--setting-sources", "local",
               "--strict-mcp-config", "--mcp-config", str(cfg), "--tools", "", "--allowedTools", "mcp__gna",
               "--system-prompt", prompt, "--no-session-persistence"]
        t0 = time.time(); err = None; events = []
        try:
            p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout)
            events = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
            if p.returncode != 0 and not events:
                err = (p.stderr or "")[:400]
        except subprocess.TimeoutExpired:
            err = f"Case timed out after {timeout}s"
    dur = int((time.time() - t0) * 1000)
    tools, results, msg_ids, final = [], {}, set(), {}
    for e in events:
        m = e.get("message") or {}
        if e.get("type") == "assistant":
            msg_ids.add(m.get("id"))
            for b in m.get("content") or []:
                if b.get("type") == "tool_use":
                    tools.append({"tool": b["name"].split("__")[-1], "input": b.get("input", {}), "id": b.get("id")})
        elif e.get("type") == "user":
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                    results[b.get("tool_use_id")] = c if isinstance(c, str) else json.dumps(c)
        elif e.get("type") == "result":
            final = e
    actions, charts = derive_actions_and_charts([(t["tool"], results.get(t["id"], "")) for t in tools])
    answer = final.get("result") or ""
    usage = final.get("usage") or {}
    out = {"answer": answer, "full_answer": answer, "tools_used": [{"tool": t["tool"], "input": t["input"]} for t in tools],
           "actions": actions, "chart_urls": charts, "usage": {"rounds": len(msg_ids), "input_tokens": usage.get("input_tokens", 0),
                                         "output_tokens": usage.get("output_tokens", 0)},
           "error": err or (answer if final.get("is_error") else None)}
    row = dataclasses.asdict(score_result(case, out, dur, float(final.get("total_cost_usd") or 0)))
    row["capability_passed"] = capability_passed(row["checks"])
    row["tool_results"] = [results.get(t["id"], "")[:1500] for t in tools]
    row["model_usage"] = list((final.get("modelUsage") or {}).keys())
    return row


def _unwrap(x):
    """Saved results may still be Claude Code's [{"type":"text","text":...}] wrapper (truncated if long)."""
    if not x.startswith("["):
        return x
    try:
        return "".join(b.get("text", "") for b in json.loads(x) if isinstance(b, dict))
    except ValueError:
        return x                                   # truncated long result: not a lookup/chart result


def rescore(path):
    """Re-score saved runs with the current scoring code (no model calls)."""
    cases = {c["id"]: c for c in load_cases(case_file=str(CASES))}
    rows = [json.loads(l) for l in open(path)]
    out = []
    for r in rows:
        raw = [_unwrap(x) for x in r.get("tool_results", [])]
        actions, charts = derive_actions_and_charts(list(zip(r["tools_used"], raw)))
        agent = {"answer": r["full_answer"], "full_answer": r["full_answer"],
                 "tools_used": r.get("tools_called") or [{"tool": t} for t in r["tools_used"]], "actions": actions,
                 "chart_urls": charts, "usage": {"rounds": r["rounds"], "input_tokens": r["input_tokens"],
                 "output_tokens": r["output_tokens"]}, "error": r.get("error")}
        new = dataclasses.asdict(score_result(cases[r["case_id"]], agent, r["duration_ms"], r["cost_usd"]))
        new["capability_passed"] = capability_passed(new["checks"])
        new.update(tool_results=raw, model_usage=r.get("model_usage"))
        out.append(new)
    with open(path, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"re-scored {len(out)} runs: capability pass {sum(r['capability_passed'] for r in out)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--ids", nargs="*")
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--rescore", action="store_true", help="re-score saved results in --out (no model calls)")
    ap.add_argument("--code-dir", help="run against another code tree (e.g. a git archive of 6576859)")
    ap.add_argument("--cases-file", help="task file (default: v7)")
    ap.add_argument("--prompt-file", help="system prompt file (default: v4)")
    a = ap.parse_args()
    if a.rescore:
        return rescore(Path(a.out) / "results.jsonl")
    cases = load_cases(case_file=a.cases_file or str(CASES), filter_ids=a.ids)
    prompt = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else PROMPT
    server = Path(a.code_dir) / "api/agent/mcp_server.py" if a.code_dir else SERVER
    (out := Path(a.out)).mkdir(parents=True, exist_ok=True)
    (out / "_run_meta.json").write_text(json.dumps({"code_dir": a.code_dir, "cases_file": a.cases_file or str(CASES),
        "prompt_file": a.prompt_file or "v4", "server": str(server)}, indent=1))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    done = set()
    if (out / "results.jsonl").exists():
        done = {json.loads(l)["case_id"] for l in open(out / "results.jsonl")}
    todo = [c for c in cases if c["id"] not in done]
    print(f"{len(todo)} to run ({len(done)} already done)", flush=True)
    with open(out / "results.jsonl", "a", encoding="utf-8") as fh, ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(run_case, c, a.timeout, prompt, server): c for c in todo}
        for f in as_completed(futs):
            c = futs[f]
            try:
                row = f.result()
            except Exception as exc:
                row = {"case_id": c["id"], "capability_passed": False, "error": f"runner: {exc}", "checks": [], "tools_used": []}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n"); fh.flush()
            print(f"{c['id']}: {'PASS' if row['capability_passed'] else 'fail'} tools={row.get('tools_used')} err={str(row.get('error'))[:60]}", flush=True)


if __name__ == "__main__":
    main()
