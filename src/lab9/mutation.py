"""Gate scorecard (M5-M7). Runs every public variant through YOUR graders + spec + gate and
compares the decision with the expected one. A regression the gate lets through is a survived
mutant; a harmless change it blocks is a false alarm. Both cost points.

    python -m lab9.mutation --spec config/metric_spec_v2.yaml --baseline reports/baseline_v2.json
    python -m lab9.mutation --spec config/metric_spec_v2.yaml --aa 66,77,88,99,110
    python -m lab9.mutation --detect          # M3: detection / false-alarm rate of your graders (v1 spec)

--aa runs swarm on a second seed set and prints the per-metric difference from the baseline run.
That is the A/A noise floor you use to pick thresholds; it is NOT a gate run (the gate rightly
refuses a report whose (item, seed) set differs from the baseline's).
The instructor runs the same loop with hidden variants and traps.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab9 import gate, variants
from lab9.eval import SPEC, load_spec, run_eval
from lab9.graders import GRADERS

EXPECTED = {
    "fixed": "merge",
    "honest_refactor": "merge",
    "seeded_regression": "block",
    "slice_regression": "block",
    "flaky_regression": "block",
}


def scorecard(spec: dict, base: dict, base_spec: dict | None) -> list[tuple[str, str, str, list[str]]]:
    variants.register()
    out = []
    for name, want in EXPECTED.items():
        blocked, _ = gate.check(run_eval(name, spec), base, spec, base_spec)
        out.append((name, want, "block" if blocked else "merge", blocked))
    return out


def detect(spec: dict) -> tuple[float, float]:
    """Detection: of the seeded_regression rows that fail pass_rate, the share that at least one of
    your other graders also flags (so you can say *why* it failed). False alarm: share of fixed rows flagged."""
    variants.register()
    # A `max` threshold counts violations (True = bad); a `min` threshold counts passes (False = bad).
    bad_value = {m["id"]: "max" in (m.get("threshold") or {}) for m in spec["metrics"]
                 if m["id"] in GRADERS and m["id"] != "pass_rate"}
    flagged = lambda r: any(r.get(k) is v for k, v in bad_value.items())
    broken = [r for r in run_eval("seeded_regression", spec)["rows"] if r.get("pass_rate") is False]
    fixed = run_eval("fixed", spec)["rows"]
    det = sum(map(flagged, broken)) / len(broken) if broken else 0.0
    return det, sum(map(flagged, fixed)) / len(fixed)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab9.mutation")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--baseline", default="reports/baseline_v2.json")
    ap.add_argument("--base-spec", help="spec of the baseline commit (ratchet check)")
    ap.add_argument("--detect", action="store_true",
                    help="M3: share of failing seeded_regression rows your graders explain (>=0.80), and of fixed rows (<=0.10)")
    ap.add_argument("--aa", help="comma-separated alternate seeds: print the A/A metric deltas")
    args = ap.parse_args(argv)
    spec = load_spec(Path(args.spec))
    variants.register()
    if args.detect:
        det, fa = detect(spec)
        ok = det >= 0.80 and fa <= 0.10
        print(f"detection {det:.2%} (target >=80%) · false alarms {fa:.2%} (target <=10%)")
        return 0 if ok else 1
    if args.aa:
        a = run_eval("swarm", spec)["metrics"]
        b = run_eval("swarm", spec, [int(x) for x in args.aa.split(",")])["metrics"]
        print(f"{'metric':<22} {'spec seeds':>10} {'alt seeds':>10} {'delta':>8}")
        for k in a:
            if isinstance(a[k], (int, float)) and isinstance(b.get(k), (int, float)):
                print(f"{k:<22} {a[k]:>10} {b[k]:>10} {b[k] - a[k]:>+8.4f}")
        return 0
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    rows = scorecard(spec, base, base_spec)
    for name, want, got, why in rows:
        tag = "ok" if want == got else ("SURVIVED" if want == "block" else "FALSE ALARM")
        print(f"  {name:<20} expect {want:<5} got {got:<5} {tag:<11} {', '.join(why)}")
    killed = sum(w == g == "block" for _, w, g, _ in rows)
    regs = sum(w == "block" for _, w, _, _ in rows)
    fa = sum(w == "merge" and g == "block" for _, w, g, _ in rows)
    print(f"mutation score {killed}/{regs} · false alarms {fa}")
    return 0 if killed == regs and fa == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
