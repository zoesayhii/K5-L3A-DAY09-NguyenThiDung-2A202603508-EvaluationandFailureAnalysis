"""Eval-gaming traps (M7, Expert). Each trap is a report or spec a careless -- or motivated --
engineer could hand the gate to turn a red build green. Your integrity_check must make the gate
exit 1 on every one of them. The instructor grades with more traps than this file builds.

    python -m lab9.traps --pr reports/eval_slice_regression.json --baseline reports/baseline_v2.json \
        --spec config/metric_spec_v2.yaml

Builds every trap, runs the gate on each one, and exits 1 if any trap gets through (exit 0 only
when the gate blocks them all). The trap files stay in reports/traps/ for re-running one by hand.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import yaml

from lab9.eval import SPEC, aggregate, load_spec


def _recompute(rep: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    ids = [m for m in rep["metrics"] if m in {x["id"] for x in spec["metrics"]} and m in rep["rows"][0]]
    rep["metrics"] = aggregate(rep["rows"], ids, k_values=spec.get("pass_k", []))
    return rep


def _bad(r: dict[str, Any], spec: dict[str, Any]) -> bool:
    """A row that fails any spec metric: a safety flag that fired, or a capability that is False."""
    for m in spec["metrics"]:
        v = r.get(m["id"])
        if (m.get("kind") == "safety" and v) or (m.get("kind") == "capability" and v is False):
            return True
    return False


def build(pr: dict[str, Any], spec: dict[str, Any]) -> dict[str, tuple[dict, dict | None]]:
    """name -> (gamed report, loosened spec or None). Every trap hides the failing evidence so a
    gate that only compares metric values against thresholds goes green."""
    ids = [m["id"] for m in spec["metrics"] if m.get("kind") == "capability" and m["id"] in pr["rows"][0]]
    out: dict[str, tuple[dict, dict | None]] = {}

    t = copy.deepcopy(pr)                             # "the grader crashed on those, ignore them"
    for r in t["rows"]:
        for m in ids:
            if r.get(m) is False:
                r[m] = None
    t = _recompute(t, spec)
    for m, v in t["metrics"].items():
        if v is None:
            t["metrics"][m] = float("nan")            # nan < min is False: a naive gate passes it
    out["evaluator_errors_as_nan"] = (t, None)

    t = copy.deepcopy(pr)                             # "those rows were flaky, I dropped them"
    t["rows"] = [r for r in t["rows"] if not _bad(r, spec)]
    out["dropped_failing_rows"] = (_recompute(t, spec), None)

    seed_bad: dict[int, int] = {}
    for r in pr["rows"]:
        seed_bad[r["seed"]] = seed_bad.get(r["seed"], 0) + _bad(r, spec)
    best = min(seed_bad.values())
    keep = sorted(s for s, b in seed_bad.items() if b == best)
    t = copy.deepcopy(pr)                             # "we only report the seeds that converged"
    t["rows"] = [r for r in t["rows"] if r["seed"] in keep]
    t["manifest"]["seeds"] = keep
    out["cherry_picked_seeds"] = (_recompute(t, spec), None)

    loose = copy.deepcopy(spec)                       # same eval-set version, laxer thresholds
    for m in loose["metrics"]:
        th = m.get("threshold", {})
        if "min" in th:
            th["min"] = round(th["min"] - 0.3, 2)
        th.pop("no_significant_drop", None)
    loose["slices"] = []
    out["loosened_spec"] = (copy.deepcopy(pr), loose)
    return out


def main(argv: list[str] | None = None) -> int:
    from lab9 import gate
    ap = argparse.ArgumentParser(prog="lab9.traps")
    ap.add_argument("--pr", required=True, help="a report the gate correctly blocks")
    ap.add_argument("--baseline", required=True, help="the baseline the gate compares against")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--out", default="reports/traps")
    args = ap.parse_args(argv)
    spec = load_spec(Path(args.spec))
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    leaked = []
    for name, (rep, sp) in build(pr, spec).items():
        p = out / f"{name}.json"
        p.write_text(json.dumps(rep, ensure_ascii=False, allow_nan=True), encoding="utf-8")
        line = f"--pr {p} --baseline {args.baseline}"
        if sp is not None:
            sp_path = out / f"{name}.spec.yaml"
            sp_path.write_text(yaml.safe_dump(sp, allow_unicode=True, sort_keys=False), encoding="utf-8")
            line += f" --spec {sp_path} --base-spec {args.spec}"
        else:
            line += f" --spec {args.spec}"
        blocked, _ = gate.check(rep, base, sp if sp is not None else spec, spec if sp is not None else None)
        verdict = "blocked" if blocked else "LEAKED "
        if not blocked:
            leaked.append(name)
        print(f"trap {name:<24} {verdict}  python -m lab9.gate {line}")
    if leaked:
        print(f"exit 1 — {len(leaked)} trap(s) got through the gate: {', '.join(leaked)}")
        return 1
    print("exit 0 — the gate blocked every public trap (the instructor runs more)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
