"""Agent variants for the CI gate (M4). Each is the Lab 8 swarm with bug switches.

    fixed              always trusts the DB (the fix for FM-03)  -> gate must exit 0
    seeded_regression  ticket_trust + pre_deducted + ignore_denied -> gate must exit 1
  v2 (M5-M7, metric_spec_v2.yaml, baseline_v2.json):
    honest_refactor    fixed + paraphrase + extra_lookup: different words/path, same outcome -> exit 0
    slice_regression   fixed + clause summing on odd seeds: the average stays above the floor and
                       its CI touches 0; only a money_movement slice gate blocks it  -> exit 1
    flaky_regression   fixed + rounding bug on 1 seed in 5: an unreliable agent    -> exit 1
  The instructor grades with more variants that are not in this file.
Registered into lab8.shapes.SHAPES at run time; no Lab 8 file is edited.
"""
from __future__ import annotations

from lab9.variant_agent import make_shape

VARIANTS = {
    "fixed": frozenset({"no_override"}),
    "seeded_regression": frozenset({"ticket_trust", "pre_deducted", "ignore_denied"}),
    "honest_refactor": frozenset({"no_override", "paraphrase", "extra_lookup"}),
    "slice_regression": frozenset({"no_override", "intermittent", "sum_parts"}),
    "flaky_regression": frozenset({"no_override", "rare", "round_down"}),
}


def register() -> list[str]:
    from lab8.shapes import SHAPES
    for name, bugs in VARIANTS.items():
        SHAPES.setdefault(name, make_shape(name, bugs))
    return list(VARIANTS)
