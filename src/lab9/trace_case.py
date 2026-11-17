"""Trace -> decision: lay one trial's reply, tool calls and ledger side by side.

    python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11

Find the FIRST wrong step, then turn that trial into a regression case
(docs/trace_case.md). Runs the shape on a fresh temp store, never the team DB.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from lab8.console import utf8_stdio
from lab8.db import load_json, load_jsonl
from lab9 import variants
from lab9.eval import WORLD, make_task


def investigate(shape: str, claim_id: str, seed: int) -> dict:
    variants.register()
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    labels = {c["claim_id"]: c["expected"] for c in claims}
    with tempfile.TemporaryDirectory(prefix="lab9-case-", ignore_cleanup_errors=True) as tmp:
        trial = make_task(shape, load_json(WORLD), claims, labels, Path(tmp))({"claim_id": claim_id, "seed": seed})
    return {"trial": trial, "label": labels[claim_id]}


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.trace_case")
    ap.add_argument("--shape", required=True)
    ap.add_argument("--claim", required=True)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args(argv)
    case = investigate(args.shape, args.claim, args.seed)
    t, label = case["trial"], case["label"]
    print(f"== {args.shape} {args.claim}@{args.seed}  lab8 grader: {'PASS' if t['lab8_pass'] else 'FAIL'} ({t['lab8_reason']})")
    print("-- trace (step, kind, payload)")
    for i, e in enumerate(t["events"], 1):
        print(f"  {i:>2} {e.get('kind', '?'):<18} {json.dumps(e.get('payload'), ensure_ascii=False)[:110]}")
    print("-- ledger vs label")
    for k in ("refund_vnd", "refund_count"):
        mark = "" if t["snapshot"].get(k) == label.get(k) else "   <-- differs"
        print(f"  {k:<14} ledger={t['snapshot'].get(k)!s:<8} label={label.get(k)}{mark}")
    print(f"  status         result={t['result'].get('status')!s:<8} label={label.get('status')}")
    print(f"  unexpected ledger rows: {t['unexpected_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
