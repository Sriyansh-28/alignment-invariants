"""Statistical procedures, with the reasoning for each choice.

The design is *within-task*: every task is evaluated under every condition, and
all interventions operate on the identical stage-1 answer. That pairing is the
single most important fact about the analysis, and it dictates the tests:

* **McNemar's exact test** for condition-vs-condition accuracy. The paired
  binary outcome (correct/incorrect on the same item) makes a two-sample
  proportion test wrong -- it would ignore the pairing and overstate the
  variance. McNemar conditions on the discordant pairs, which is exactly the
  information the pairing provides. The *exact* (binomial) version is used
  rather than the chi-square approximation because the discordant counts here
  are small (often < 10), where the asymptotic version is anticonservative.

* **Wilson score intervals** for single proportions. With n around 27 and
  proportions that can sit near 0 or 1, the normal-approximation (Wald)
  interval both undercovers and can extend outside [0, 1]. Wilson does not.

* **Bootstrap (BCa-free percentile, clustered on task)** for differences in
  rates whose denominators are themselves random (correction rates, where the
  denominator is "number of initial errors"). A closed-form interval is not
  available for a ratio with a random denominator; resampling tasks preserves
  the dependence between the numerator and denominator.

* **Cochran's Q** as an omnibus test across all six conditions before pairwise
  comparisons, so the pairwise tests are not fishing in an undifferentiated
  set.

* **Holm-Bonferroni** for multiplicity. Holm is uniformly more powerful than
  Bonferroni and, unlike Benjamini-Hochberg, controls the family-wise error
  rate -- appropriate here because the claims are about specific named
  comparisons, not about a discovery set.

* **Cochran-Armitage trend test** for the difficulty ladder, because difficulty
  is ordered (1 < 2 < 3) and a test that ignores the ordering throws away the
  structure the experiment was built around.

A note on power: with 27 paired items this study is small. ``mde_paired``
reports the minimum detectable effect so that null results can be read as
"underpowered to detect less than X" rather than as evidence of no effect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Sequence

import numpy as np
from scipy import stats


@dataclass
class Interval:
    point: float | None
    low: float | None
    high: float | None
    method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    name: str
    statistic: float | None
    p_value: float | None
    effect: dict[str, Any]
    n: int
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Interval estimation
# ---------------------------------------------------------------------------

def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return Interval(None, None, None, "wilson (undefined: n=0)")
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half), "wilson")


def bootstrap_rate_ci(numer_flags: Sequence[bool], denom_flags: Sequence[bool],
                      n_boot: int = 10000, confidence: float = 0.95,
                      seed: int = 12345) -> Interval:
    """Percentile bootstrap for a rate whose denominator is random.

    ``denom_flags[i]`` marks whether item i belongs to the denominator (e.g.
    "was initially wrong"); ``numer_flags[i]`` whether it also belongs to the
    numerator (e.g. "and ended up correct"). Tasks are resampled jointly so the
    correlation between numerator and denominator is preserved.
    """
    numer = np.asarray(numer_flags, dtype=bool)
    denom = np.asarray(denom_flags, dtype=bool)
    n = len(denom)
    if n == 0 or denom.sum() == 0:
        return Interval(None, None, None, "bootstrap (undefined: empty denominator)")

    point = float(numer.sum() / denom.sum())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    d = denom[idx].sum(axis=1)
    nu = numer[idx].sum(axis=1)
    valid = d > 0
    if valid.sum() < 100:
        return Interval(point, None, None, "bootstrap (too few valid resamples)")
    rates = nu[valid] / d[valid]
    alpha = (1 - confidence) / 2
    lo, hi = np.quantile(rates, [alpha, 1 - alpha])
    return Interval(point, float(lo), float(hi),
                    f"percentile bootstrap ({int(valid.sum())} resamples)")


def bootstrap_paired_diff(a: Sequence[bool], b: Sequence[bool],
                          n_boot: int = 10000, confidence: float = 0.95,
                          seed: int = 12345) -> Interval:
    """Percentile bootstrap CI for the paired difference in means (b - a)."""
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if len(x) != len(y) or len(x) == 0:
        return Interval(None, None, None, "bootstrap (undefined)")
    point = float(y.mean() - x.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    diffs = y[idx].mean(axis=1) - x[idx].mean(axis=1)
    alpha = (1 - confidence) / 2
    lo, hi = np.quantile(diffs, [alpha, 1 - alpha])
    return Interval(point, float(lo), float(hi), "paired percentile bootstrap")


# ---------------------------------------------------------------------------
# Hypothesis tests
# ---------------------------------------------------------------------------

def mcnemar_exact(a: Sequence[bool], b: Sequence[bool], name: str = "mcnemar") -> TestResult:
    """Exact McNemar test on paired binary outcomes.

    ``a`` and ``b`` are aligned per-item correctness vectors. Only discordant
    pairs carry information: b01 (a right, b wrong) and b10 (a wrong, b right).
    Under H0 each discordant pair is equally likely to fall either way, so the
    count is Binomial(n_discordant, 0.5).
    """
    x = np.asarray(a, dtype=bool)
    y = np.asarray(b, dtype=bool)
    if len(x) != len(y):
        raise ValueError("paired vectors must be the same length")
    b01 = int(np.sum(x & ~y))   # correct under a, wrong under b
    b10 = int(np.sum(~x & y))   # wrong under a, correct under b
    n_disc = b01 + b10
    if n_disc == 0:
        return TestResult(name, statistic=0.0, p_value=1.0,
                          effect={"b01": 0, "b10": 0, "n_discordant": 0,
                                  "risk_difference": 0.0,
                                  "odds_ratio": None},
                          n=len(x),
                          note="no discordant pairs; test carries no information")
    p = float(stats.binomtest(b10, n_disc, 0.5).pvalue)
    rd = float(y.mean() - x.mean())
    or_ = (b10 / b01) if b01 > 0 else None
    return TestResult(
        name, statistic=float(b10), p_value=p,
        effect={"b01": b01, "b10": b10, "n_discordant": n_disc,
                "risk_difference": rd, "odds_ratio": or_,
                "acc_a": float(x.mean()), "acc_b": float(y.mean())},
        n=len(x),
        note="exact binomial McNemar on discordant pairs")


def cochran_q(condition_vectors: dict[str, Sequence[bool]]) -> TestResult:
    """Cochran's Q: omnibus test for k paired binary conditions.

    Answers "is any condition different from any other?" before pairwise tests
    are inspected, which keeps the pairwise comparisons from being a fishing
    expedition over an undifferentiated set.
    """
    names = list(condition_vectors)
    mat = np.array([np.asarray(condition_vectors[n], dtype=int) for n in names])
    k, n = mat.shape
    if k < 2:
        return TestResult("cochran_q", None, None, {}, n, "needs >= 2 conditions")
    col = mat.sum(axis=0)          # per-item successes across conditions
    row = mat.sum(axis=1)          # per-condition totals
    total = int(mat.sum())
    denom = (k * total - int((col ** 2).sum()))
    if denom == 0:
        return TestResult("cochran_q", None, None, {"conditions": names}, n,
                          "degenerate: identical outcomes across all conditions")
    q = (k - 1) * (k * int((row ** 2).sum()) - total ** 2) / denom
    p = float(stats.chi2.sf(q, k - 1))
    return TestResult("cochran_q", float(q), p,
                      {"conditions": names, "df": k - 1,
                       "per_condition_accuracy": {nm: float(np.mean(condition_vectors[nm]))
                                                  for nm in names}},
                      n, "omnibus test across paired conditions")


def cochran_armitage_trend(successes: Sequence[int], totals: Sequence[int],
                           scores: Sequence[float] | None = None) -> TestResult:
    """Cochran-Armitage test for a monotone trend in proportions across ordered
    groups (here: difficulty 1 < 2 < 3).

    Chosen over a 3xk chi-square because difficulty is ordered; the chi-square
    would treat the levels as unordered categories and discard that structure.
    """
    s = np.asarray(successes, dtype=float)
    nvec = np.asarray(totals, dtype=float)
    if len(s) != len(nvec) or nvec.sum() == 0:
        return TestResult("cochran_armitage", None, None, {}, 0, "undefined")
    x = np.asarray(scores if scores is not None else range(1, len(s) + 1), dtype=float)
    n_tot = nvec.sum()
    p_bar = s.sum() / n_tot
    if p_bar in (0.0, 1.0):
        return TestResult("cochran_armitage", None, None,
                          {"proportions": (s / np.maximum(nvec, 1)).tolist()},
                          int(n_tot),
                          "degenerate: all outcomes identical, no trend defined")
    x_bar = float((nvec * x).sum() / n_tot)
    num = float((x - x_bar).dot(s - nvec * p_bar))
    var = float(p_bar * (1 - p_bar) * (nvec * (x - x_bar) ** 2).sum())
    if var <= 0:
        return TestResult("cochran_armitage", None, None, {}, int(n_tot), "zero variance")
    z = num / math.sqrt(var)
    p = float(2 * stats.norm.sf(abs(z)))
    return TestResult("cochran_armitage", float(z), p,
                      {"proportions": (s / np.maximum(nvec, 1)).tolist(),
                       "scores": x.tolist(),
                       "direction": "increasing" if z > 0 else "decreasing"},
                      int(n_tot),
                      "trend across ordered difficulty levels")


# ---------------------------------------------------------------------------
# Multiplicity and power
# ---------------------------------------------------------------------------

def holm_bonferroni(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict[str, Any]]:
    """Holm-Bonferroni step-down adjustment, controlling family-wise error rate.

    Returns adjusted p-values and the reject decision at ``alpha``. Comparisons
    with a missing p-value (undefined test) are excluded from the family rather
    than counted, since including them would inflate the correction.
    """
    items = [(k, v) for k, v in pvalues.items() if v is not None]
    m = len(items)
    if m == 0:
        return {}
    items.sort(key=lambda kv: kv[1])
    out: dict[str, dict[str, Any]] = {}
    running = 0.0
    for i, (name, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)   # enforce monotonicity
        out[name] = {"p_raw": p, "p_adjusted": running,
                     "reject_at_alpha": running < alpha, "rank": i + 1,
                     "family_size": m}
    return out


def mde_paired(n_pairs: int, discordance_rate: float = 0.3,
               alpha: float = 0.05, power: float = 0.80) -> dict[str, Any]:
    """Approximate minimum detectable effect for a paired binary comparison.

    Reported so that a null result can be stated as "underpowered to detect a
    difference smaller than X" instead of being misread as evidence of no
    effect. Uses the normal approximation to the McNemar test.
    """
    if n_pairs <= 0:
        return {"n_pairs": n_pairs, "mde_risk_difference": None}
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    n_disc = max(1.0, n_pairs * discordance_rate)
    # difference in discordant proportions detectable at the given power
    delta_disc = (z_a + z_b) / math.sqrt(n_disc)
    mde = min(1.0, delta_disc * discordance_rate)
    return {"n_pairs": n_pairs,
            "assumed_discordance_rate": discordance_rate,
            "alpha": alpha, "power": power,
            "mde_risk_difference": float(mde),
            "note": "normal approximation; treat as an order-of-magnitude guide"}
