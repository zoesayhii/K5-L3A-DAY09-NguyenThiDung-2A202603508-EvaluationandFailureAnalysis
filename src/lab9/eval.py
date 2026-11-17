"""Eval harness: one command, one report with a run ID you can re-check.

    python -m lab9.eval --shape workflow
    python -m lab9.eval --shape swarm --out reports/baseline_v1.json
    python -m lab9.eval --shape swarm --spec config/metric_spec_v2.yaml --out reports/baseline_v2.json
    python -m lab9.eval --shape swarm --seeds 66,77,88,99,110   # A/A noise check (M6)

Each (item, seed) is one pydantic-evals Case. The task runs the shape on a fresh
SQLite store and returns a Trial; graders in lab9.graders score it. Reports are
written by this script only -- never edit reports/ by hand.
"""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic_evals import Case, Dataset

from lab8.benchmark import prepare_from_memory, run_trial
from lab8.console import utf8_stdio
from lab8.db import connect, load_json, load_jsonl
from lab8.metrics import artifact_blob, ledger_snapshot, trial_pass, unexpected_ledger_rows
from lab9 import evalset, stats, variants
from lab9.graders import GRADERS

SPEC = Path("config/metric_spec.yaml")
WORLD = Path("data/public_world_state.json")


def load_spec(path: Path = SPEC) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_task(shape: str, world: dict[str, Any], claims: list[dict[str, Any]], labels: dict[str, Any], tmp: Path):
    def run_one(inputs: dict[str, Any]) -> dict[str, Any]:
        claim_id, seed = inputs["claim_id"], inputs["seed"]
        store = tmp / f"{shape}-{claim_id}-{seed}.sqlite"
        prepare_from_memory(store, world, claims)
        started = time.time()
        payload, error = run_trial(shape, claim_id, seed, store)
        conn = connect(store)
        try:
            if payload is None:
                return {"result": {"claim_id": claim_id, "status": "error", "error_reason": error},
                        "snapshot": ledger_snapshot(conn, claim_id), "unexpected_rows": unexpected_ledger_rows(conn, claim_id),
                        "blob": "", "events": [], "lab8_pass": False, "lab8_reason": error}
            ok, reason = trial_pass(payload, labels[claim_id], conn, started_at=started)
            events = []
            trace_path = Path(payload.get("trace_path") or "")
            if trace_path.is_file():
                events = json.loads(trace_path.read_text(encoding="utf-8")).get("events", [])
            return {"result": payload, "snapshot": {k: v for k, v in ledger_snapshot(conn, claim_id).items() if k != "effect"},
                    "unexpected_rows": unexpected_ledger_rows(conn, claim_id), "blob": artifact_blob(payload),
                    "events": events, "lab8_pass": ok, "lab8_reason": reason}
        finally:
            conn.close()
    return run_one


def load_world(spec: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Lab 8 world + public claims, plus the adversarial pack when the spec names one (v2).
    The pack only ADDS claims and approvals in memory; no Lab 8 file is touched."""
    world = load_json(WORLD)
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    if spec.get("adversarial_pack"):
        pack = json.loads(Path(spec["adversarial_pack"]).read_text(encoding="utf-8"))
        world = {**world, "approvals": [*world["approvals"], *pack["approvals"]]}
        claims = [*claims, *pack["claims"]]
    return world, claims


def run_eval(shape: str, spec: dict[str, Any], seeds: list[int] | None = None) -> dict[str, Any]:
    items = evalset.load_jsonl(Path(spec["eval_set"]))
    labels = json.loads(Path(spec["labels"]).read_text(encoding="utf-8"))
    world, claims = load_world(spec)
    seeds = list(seeds or spec["seeds"])
    slices_of = {it["item_id"]: list(it.get("slices") or []) for it in items}
    metric_ids = [m["id"] for m in spec["metrics"] if m["id"] in GRADERS]
    cases = [Case(name=f"{it['item_id']}@{s}", inputs={"claim_id": it["claim_id"], "seed": s},
                  expected_output=labels[it["claim_id"]], metadata={"item_id": it["item_id"], "seed": s})
             for it in items for s in seeds]
    dataset = Dataset(name=f"logix-{spec['eval_set_version']}", cases=cases,
                      evaluators=[GRADERS[m]() for m in metric_ids])
    with tempfile.TemporaryDirectory(prefix="lab9-eval-", ignore_cleanup_errors=True) as tmp:
        # max_concurrency=1: shapes write traces/ and SQLite; keep runs deterministic.
        report = dataset.evaluate_sync(make_task(shape, world, claims, labels, Path(tmp)),
                                       max_concurrency=1, progress=False)
    rows = []
    for c in report.cases:
        scores = {}
        for m, g in zip(metric_ids, (GRADERS[m].__name__ for m in metric_ids)):
            res = c.assertions.get(g)
            scores[m] = None if res is None else bool(res.value)
        rows.append({"item_id": c.metadata["item_id"], "seed": c.metadata["seed"],
                     "slices": slices_of.get(c.metadata["item_id"], []), **scores,
                     "cost": float(c.output["result"].get("cost_estimate") or 0.0)})
    failures = [f"{c.name}:{f.name}:{f.error_message[:80]}" for c in report.cases for f in c.evaluator_failures]
    eval_set_sha = evalset.sha12(Path(spec["eval_set"]))
    run_id = f"E-{shape}-{date.today():%Y%m%d}-{eval_set_sha[:4]}"
    return {"run_id": run_id, "shape": shape,
            "manifest": {"eval_set": spec["eval_set"], "eval_set_sha": eval_set_sha, "items": len(items),
                         "seeds": seeds, "metric_spec_version": spec["metric_spec_version"],
                         "llm": "MockLLM", "python": platform.python_version()},
            "rows": rows, "evaluator_failures": failures,
            "metrics": aggregate(rows, metric_ids, k_values=spec.get("pass_k", []))}


def aggregate(rows: list[dict[str, Any]], metric_ids: list[str], k_values: list[int] = ()) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m in metric_ids:
        vals = [r[m] for r in rows if r[m] is not None]
        if m in ("secret_leak", "approval_bypass"):
            out[m] = sum(vals)                       # safety: a count, must be 0
        else:
            out[m] = round(sum(vals) / len(vals), 4) if vals else None
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        by_item.setdefault(r["item_id"], []).append(bool(r.get("pass_rate")))
    out["pass_5"] = round(sum(all(v) for v in by_item.values()) / len(by_item), 4) if by_item else None
    # pass@k / pass^k (M6): mean over items of the unbiased per-item estimate.
    # Left as None until stats.pass_at_k / stats.pass_hat_k are implemented.
    for k in k_values:
        for name, fn in (("pass_at", stats.pass_at_k), ("pass_hat", stats.pass_hat_k)):
            if not by_item or min(len(v) for v in by_item.values()) < k:
                out[f"{name}_{k}"] = None            # undefined with fewer than k runs per item
                continue
            try:
                est = [fn(len(v), sum(v), k) for v in by_item.values()]
                out[f"{name}_{k}"] = round(sum(est) / len(est), 4) if est else None
            except NotImplementedError:
                out[f"{name}_{k}"] = None
    passes = sum(bool(r.get("pass_rate")) for r in rows)
    out["cost_per_success"] = round(sum(r["cost"] for r in rows) / passes, 4) if passes else None
    return out


def per_item(report: dict[str, Any], metric: str, slice_name: str | None = None) -> dict[str, float]:
    """Mean over seeds for each item -- the unit the paired bootstrap resamples.
    With slice_name, keep only rows whose item carries that slice tag (M5)."""
    acc: dict[str, list[float]] = {}
    for r in report["rows"]:
        if slice_name is not None and slice_name not in (r.get("slices") or []):
            continue
        if r.get(metric) is not None:
            acc.setdefault(r["item_id"], []).append(float(r[metric]))
    return {k: sum(v) / len(v) for k, v in acc.items()}


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.eval")
    ap.add_argument("--shape", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--out")
    ap.add_argument("--seeds", help="comma-separated seeds overriding the spec (A/A noise check)")
    args = ap.parse_args(argv)
    spec = load_spec(Path(args.spec))
    variants.register()
    seeds = [int(x) for x in args.seeds.split(",")] if args.seeds else None
    rep = run_eval(args.shape, spec, seeds)
    out = Path(args.out or f"reports/eval_{args.shape}.json")
    m = rep["manifest"]
    print(f"{rep['run_id']} · eval set {m['eval_set_sha']} · {m['items']} item × {len(m['seeds'])} seed · {m['llm']}")
    for k, v in rep["metrics"].items():
        print(f"  {k:<22} {v}")
    if rep["evaluator_failures"]:
        print(f"  {len(rep['evaluator_failures'])} evaluator failure(s), first: {rep['evaluator_failures'][0]}")
        print(f"  not writing {out}: a report with broken graders must not become a baseline")
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
