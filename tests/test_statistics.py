"""Statistical procedures are checked against hand-computed values.

Every expected number in this file is derived analytically in the comment above
it, so a failure means the implementation drifted, not that a reference library
changed.
"""

from __future__ import annotations

import math

import pytest

from analysis.statistical_tests import (bootstrap_paired_diff, bootstrap_rate_ci,
                                        cochran_armitage_trend, cochran_q,
                                        holm_bonferroni, mcnemar_exact,
                                        mde_paired, wilson_interval)


class TestWilson:
    def test_midpoint_matches_closed_form(self):
        # p=0.5, n=10, z=1.959964: centre = 0.5, half-width =
        # 1.959964*sqrt(0.25/10 + 3.8415/400) / (1 + 0.38415) = 0.26340
        ci = wilson_interval(5, 10)
        assert ci.point == pytest.approx(0.5)
        assert ci.low == pytest.approx(0.2366, abs=1e-3)
        assert ci.high == pytest.approx(0.7634, abs=1e-3)

    def test_boundary_stays_in_unit_interval(self):
        """The reason Wilson is used instead of Wald: Wald would go negative."""
        ci = wilson_interval(0, 12)
        assert ci.low == pytest.approx(0.0, abs=1e-12)
        assert ci.low >= 0.0
        assert 0.0 < ci.high < 1.0
        ci = wilson_interval(12, 12)
        assert ci.high == pytest.approx(1.0, abs=1e-12)
        assert ci.high <= 1.0
        assert 0.0 < ci.low < 1.0

    def test_undefined_for_zero_n(self):
        ci = wilson_interval(0, 0)
        assert ci.point is None and ci.low is None


class TestMcNemar:
    def test_exact_p_matches_binomial(self):
        # 1 pair correct->wrong, 8 pairs wrong->correct, 9 discordant.
        # two-sided p = 2 * P(X >= 8 | n=9, p=.5) = 2*(9+1)/512 = 0.0390625
        a = [True] + [False] * 8 + [True] * 3
        b = [False] + [True] * 8 + [True] * 3
        r = mcnemar_exact(a, b)
        assert r.effect["b01"] == 1
        assert r.effect["b10"] == 8
        assert r.p_value == pytest.approx(0.0390625, abs=1e-9)

    def test_no_discordant_pairs_is_uninformative(self):
        a = [True, False, True, False]
        r = mcnemar_exact(a, list(a))
        assert r.p_value == 1.0
        assert r.effect["n_discordant"] == 0
        assert "no discordant" in r.note

    def test_risk_difference_sign(self):
        a = [False, False, False, False]
        b = [True, True, True, False]
        r = mcnemar_exact(a, b)
        assert r.effect["risk_difference"] == pytest.approx(0.75)

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError):
            mcnemar_exact([True], [True, False])


class TestCochranQ:
    def test_matches_hand_computation(self):
        # k=3, n=6. Condition totals G = (6, 3, 0); item totals L = (2,2,2,1,1,1)
        # T = 9, sum G^2 = 45, sum L^2 = 15
        # Q = 2*(3*45 - 81)/(3*9 - 15) = 2*54/12 = 9.0, df = 2
        vectors = {
            "c1": [1, 1, 1, 1, 1, 1],
            "c2": [1, 1, 1, 0, 0, 0],
            "c3": [0, 0, 0, 0, 0, 0],
        }
        r = cochran_q({k: [bool(x) for x in v] for k, v in vectors.items()})
        assert r.statistic == pytest.approx(9.0)
        assert r.effect["df"] == 2
        assert r.p_value == pytest.approx(0.011109, abs=1e-5)

    def test_identical_conditions_flagged_degenerate(self):
        v = [True, True, False]
        r = cochran_q({"a": v, "b": list(v), "c": list(v)})
        assert r.p_value is None
        assert "degenerate" in r.note


class TestCochranArmitage:
    def test_detects_decreasing_trend(self):
        # accuracy 9/10, 5/10, 1/10 across ordered difficulty levels
        r = cochran_armitage_trend([9, 5, 1], [10, 10, 10])
        assert r.p_value is not None and r.p_value < 0.01
        assert r.effect["direction"] == "decreasing"

    def test_flat_profile_is_not_significant(self):
        r = cochran_armitage_trend([5, 5, 5], [10, 10, 10])
        assert r.p_value == pytest.approx(1.0, abs=1e-6)

    def test_degenerate_all_correct(self):
        r = cochran_armitage_trend([10, 10, 10], [10, 10, 10])
        assert r.p_value is None
        assert "degenerate" in r.note


class TestHolm:
    def test_step_down_adjustment(self):
        # sorted p: .01 (x3), .02 (x2), .04 (x1) -> .03, .04, .04 after
        # monotonicity enforcement
        adj = holm_bonferroni({"a": 0.01, "b": 0.02, "c": 0.04})
        assert adj["a"]["p_adjusted"] == pytest.approx(0.03)
        assert adj["b"]["p_adjusted"] == pytest.approx(0.04)
        assert adj["c"]["p_adjusted"] == pytest.approx(0.04)

    def test_monotonicity_is_enforced(self):
        adj = holm_bonferroni({"a": 0.04, "b": 0.041, "c": 0.9})
        vals = [adj[k]["p_adjusted"] for k in ("a", "b", "c")]
        assert vals == sorted(vals), "adjusted p-values must be non-decreasing"

    def test_undefined_tests_excluded_from_family(self):
        adj = holm_bonferroni({"a": 0.01, "b": None, "c": 0.02})
        assert "b" not in adj
        assert adj["a"]["family_size"] == 2  # not 3


class TestBootstrap:
    def test_rate_ci_brackets_point_estimate(self):
        denom = [True] * 20 + [False] * 10
        numer = [True] * 12 + [False] * 8 + [False] * 10
        ci = bootstrap_rate_ci(numer, denom, n_boot=2000, seed=1)
        assert ci.point == pytest.approx(12 / 20)
        assert ci.low <= ci.point <= ci.high

    def test_rate_ci_undefined_when_denominator_empty(self):
        ci = bootstrap_rate_ci([False] * 5, [False] * 5, n_boot=100)
        assert ci.point is None
        assert "undefined" in ci.method

    def test_paired_diff_is_deterministic_under_seed(self):
        a = [True, False, True, False, True]
        b = [True, True, True, False, True]
        c1 = bootstrap_paired_diff(a, b, n_boot=1000, seed=7)
        c2 = bootstrap_paired_diff(a, b, n_boot=1000, seed=7)
        assert c1.low == c2.low and c1.high == c2.high
        assert c1.point == pytest.approx(0.2)


class TestPower:
    def test_mde_shrinks_with_sample_size(self):
        small = mde_paired(20)["mde_risk_difference"]
        large = mde_paired(200)["mde_risk_difference"]
        assert large < small

    def test_mde_defined_for_study_size(self):
        r = mde_paired(27)
        assert 0.0 < r["mde_risk_difference"] <= 1.0
