"""M0: environment check in < 10 s. python -m lab9.smoke"""
from __future__ import annotations
import importlib, sys
from pathlib import Path


def main() -> int:
    ok = True
    for mod in ("pydantic_evals", "scipy", "numpy", "yaml", "lab8.benchmark"):
        try:
            importlib.import_module(mod); print(f"ok   import {mod}")
        except Exception as e:  # noqa: BLE001
            ok = False; print(f"FAIL import {mod}: {e}")
    for p in ("data/public_claims.jsonl", "config/metric_spec.yaml", "data/eval/judge_tone_public.csv"):
        exists = Path(p).is_file(); ok &= exists; print(f"{'ok  ' if exists else 'FAIL'} file {p}")
    print("M0 PASS" if ok else "M0 FAIL (run from src/)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
