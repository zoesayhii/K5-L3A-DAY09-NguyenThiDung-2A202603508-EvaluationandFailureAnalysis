"""CI sanity checks on what the team committed (run by the eval-gate job).

    python -m lab9.ci_check --pr reports/eval_pr.json --baseline reports/baseline_v1.json --spec config/metric_spec.yaml

1. The baseline is a swarm run on the current eval set, and its metrics equal the CI's own swarm run.
   A baseline taken from another shape (e.g. `fixed`) or hand-edited makes every gate decision moot.
2. The spec has at least one blocking capability metric of your own (M3, the FM-08 catcher) and
   a grader for it is registered in lab9.graders.GRADERS.
Exit 0 = ok, 1 = a problem is printed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab9.eval import SPEC, load_spec
from lab9.graders import GRADERS

STARTER_METRICS = {"approval_bypass", "secret_leak", "db_fact_kept", "refund_amount_correct",
                   "pass_rate", "pass_5", "cost_per_success"}


def _same(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9
    return a == b


def check(pr: dict, base: dict, spec: dict) -> list[str]:
    problems = []
    if base.get("shape") != "swarm":
        problems.append(f"baseline shape is {base.get('shape')!r}, must be 'swarm' (re-run it on main)")
    if base.get("manifest", {}).get("eval_set_sha") != pr.get("manifest", {}).get("eval_set_sha"):
        problems.append("baseline eval_set_sha differs from the current eval set: re-run the baseline")
    shared = sorted(base.get("metrics", {}).keys() & pr.get("metrics", {}).keys())
    for k in shared:
        if not _same(base["metrics"][k], pr["metrics"][k]):
            problems.append(f"baseline metric {k} differs from CI's swarm run: re-run, never hand-edit")
    own = [m for m in spec["metrics"] if m["id"] not in STARTER_METRICS
           and m.get("kind") == "capability" and m.get("blocking")]
    if not own:
        problems.append("spec has no blocking capability metric of your own (M3: the FM-08 catcher)")
    for m in own:
        if m["id"] not in GRADERS:
            problems.append(f"metric {m['id']} has no grader registered in lab9.graders.GRADERS")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab9.ci_check")
    ap.add_argument("--pr", required=True, help="the CI's own swarm report")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    a = ap.parse_args(argv)
    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    problems = check(read(a.pr), read(a.baseline), load_spec(Path(a.spec)))
    for p in problems:
        print(f"  {p}")
    print("exit 1 — fix the above" if problems else "exit 0 — baseline and spec look sound")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
