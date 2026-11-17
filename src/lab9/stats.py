"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    tp = fp = fn = tn = 0
    for expected, actual in zip(human, judge):
        if expected == POS and actual == POS:
            tp += 1
        elif expected != POS and actual == POS:
            fp += 1
        elif expected == POS and actual != POS:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    counts = confusion(human, judge)
    precision_denominator = counts["tp"] + counts["fp"]
    recall_denominator = counts["tp"] + counts["fn"]
    precision = counts["tp"] / precision_denominator if precision_denominator else 0.0
    recall = counts["tp"] / recall_denominator if recall_denominator else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    if len(human) != len(judge) or not human:
        raise ValueError("labels must have the same non-zero length")
    n = len(human)
    observed = sum(a == b for a, b in zip(human, judge)) / n
    human_counts = {label: human.count(label) for label in set(human) | set(judge)}
    judge_counts = {label: judge.count(label) for label in human_counts}
    expected = sum(human_counts[label] * judge_counts[label] for label in human_counts) / (n * n)
    if expected == 1:
        raise ValueError("kappa is undefined for a constant judge")
    return (observed - expected) / (1 - expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denominator = sensitivity + specificity - 1
    if denominator <= 0:
        raise ValueError("sensitivity and specificity do not identify the prevalence")
    estimate = (observed_rate + specificity - 1) / denominator
    return min(1.0, max(0.0, estimate))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if len(a) != len(b) or not a:
        raise ValueError("paired samples must have the same non-zero length")
    import numpy as np
    from scipy.stats import bootstrap

    left = np.asarray(a, dtype=float)
    right = np.asarray(b, dtype=float)
    difference = left - right
    observed = float(np.mean(difference))
    if np.all(difference == 0):
        return 0.0, 0.0, 0.0
    result = bootstrap(
        (left, right),
        lambda x, y, axis: np.mean(x - y, axis=axis),
        paired=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    return observed, float(result.confidence_interval.low), float(result.confidence_interval.high)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if n < 0 or c < 0 or c > n or k <= 0 or k > n:
        raise ValueError("require 0 <= c <= n and 0 < k <= n")
    from math import comb
    return 1.0 - comb(n - c, k) / comb(n, k) if n - c >= k else 1.0


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    if n < 0 or c < 0 or c > n or k <= 0 or k > n:
        raise ValueError("require 0 <= c <= n and 0 < k <= n")
    from math import comb
    return comb(c, k) / comb(n, k) if c >= k else 0.0
