"""M2/M4 self-check. Run: python -m pytest -q -m student -o addopts= -k lab9"""
import csv
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
TONE = Path("data/eval/judge_tone_public.csv")


@pytest.fixture(scope="module")
def stats():
    # The overlaid Lab 8 CI collects these tests with only Lab 8 dependencies.
    from lab9 import stats

    return stats


def _labels():
    rows = list(csv.DictReader(TONE.open(encoding="utf-8")))
    return [r["human"] for r in rows], [r["judge"] for r in rows]


def test_confusion_tone(stats):
    assert stats.confusion(*_labels()) == {"tp": 24, "fp": 4, "fn": 6, "tn": 66}


def test_precision_recall_kappa_tone(stats):
    p, r = stats.precision_recall(*_labels())
    assert (round(p, 3), round(r, 3)) == (0.857, 0.8)
    assert round(stats.cohen_kappa(*_labels()), 3) == 0.757


def test_kappa_undefined_for_constant_judge(stats):
    with pytest.raises(ValueError):
        stats.cohen_kappa(["PASS"] * 5, ["PASS"] * 5)


def test_rogan_gladen_clips(stats):
    assert stats.rogan_gladen(0.28, 0.8, 66 / 70) == pytest.approx(0.3, abs=0.01)
    assert stats.rogan_gladen(0.0, 0.8, 0.9) == 0.0


def test_paired_bootstrap_reference(stats):
    d, lo, hi = stats.paired_bootstrap([1, 1, 0.8, 1, 0.6], [1, 0.8, 0.8, 0.6, 0.6])
    assert d == pytest.approx(0.12, abs=1e-9)
    assert lo == pytest.approx(0.0, abs=0.01) and hi == pytest.approx(0.28, abs=0.01)


def test_paired_bootstrap_identical_is_zero(stats):
    assert stats.paired_bootstrap([1, 0, 1], [1, 0, 1]) == (0.0, 0.0, 0.0)
