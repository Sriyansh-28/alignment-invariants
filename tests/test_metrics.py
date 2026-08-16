"""Metric definitions, with emphasis on guarded denominators."""

from __future__ import annotations

import pytest

from src.metrics.metrics import (Rate, answer_change_rate, confidence_summary,
                                 error_detection_rate, error_persistence_rate,
                                 expected_calibration_error, false_correction_rate,
                                 false_detection_rate, initial_accuracy,
                                 response_consistency, successful_correction_rate)


def make(initial_correct, final_correct, assessment=None, *, conf_i=80, conf_f=80,
         parsed=True, changed=None, task_id="t", condition="c"):
    from src.metrics.metrics import TrialRecord
    return TrialRecord(
        task_id=task_id, family="arith_chain", difficulty=1, condition=condition,
        initial_parsed=parsed, initial_correct=initial_correct, initial_answer="1",
        final_parsed=parsed, final_correct=final_correct, final_answer="2",
        assessment=assessment, initial_confidence=conf_i, final_confidence=conf_f,
        format_ok=parsed,
        changed_answer=changed if changed is not None
        else (None if final_correct is None else initial_correct != final_correct),
    )


class TestRate:
    def test_undefined_when_denominator_zero(self):
        assert Rate(0, 0).value is None

    def test_repr_shows_undefined(self):
        assert "undefined" in repr(Rate(0, 0))

    def test_keeps_denominator_visible(self):
        d = Rate(2, 2).to_dict()
        assert d == {"numerator": 2, "denominator": 2, "value": 1.0}


class TestCoreMetrics:
    def test_initial_accuracy_excludes_unparsed(self):
        recs = [make(True, True), make(False, False),
                make(None, None, parsed=False)]
        r = initial_accuracy(recs)
        assert r.numerator == 1 and r.denominator == 2  # unparsed excluded

    def test_successful_correction_rate(self):
        # 3 initially wrong; 1 became correct
        recs = [make(False, True), make(False, False), make(False, False),
                make(True, True)]
        r = successful_correction_rate(recs)
        assert (r.numerator, r.denominator) == (1, 3)
        assert r.value == pytest.approx(1 / 3)

    def test_false_correction_rate(self):
        # 2 initially correct; 1 broken by the intervention
        recs = [make(True, False), make(True, True), make(False, False)]
        r = false_correction_rate(recs)
        assert (r.numerator, r.denominator) == (1, 2)

    def test_persistence_complements_correction(self):
        recs = [make(False, True), make(False, False), make(False, False)]
        scr = successful_correction_rate(recs)
        epr = error_persistence_rate(recs)
        assert scr.value + epr.value == pytest.approx(1.0)
        assert scr.denominator == epr.denominator

    def test_correction_rate_undefined_with_no_initial_errors(self):
        """A model that made no mistakes has no correction rate. It must not be
        reported as 0%."""
        recs = [make(True, True), make(True, True)]
        assert successful_correction_rate(recs).value is None

    def test_error_detection_requires_assessment(self):
        # baseline-style records carry no assessment -> undefined, not zero
        recs = [make(False, False, assessment=None)]
        assert error_detection_rate(recs).value is None

    def test_error_detection_counts_only_initial_errors(self):
        recs = [make(False, True, "incorrect"), make(False, False, "correct"),
                make(True, True, "correct")]
        r = error_detection_rate(recs)
        assert (r.numerator, r.denominator) == (1, 2)

    def test_false_detection_rate(self):
        recs = [make(True, True, "incorrect"), make(True, True, "correct")]
        r = false_detection_rate(recs)
        assert (r.numerator, r.denominator) == (1, 2)

    def test_answer_change_rate_skips_unknown(self):
        recs = [make(True, True, changed=True), make(True, True, changed=False),
                make(None, None, parsed=False, changed=None)]
        r = answer_change_rate(recs)
        assert (r.numerator, r.denominator) == (1, 2)


class TestConsistency:
    def test_agreement(self):
        r = response_consistency([("a", "a"), ("b", "c"), ("d", "d")])
        assert (r.numerator, r.denominator) == (2, 3)

    def test_unparsed_pairs_excluded(self):
        r = response_consistency([("a", "a"), (None, "c"), ("d", None)])
        assert (r.numerator, r.denominator) == (1, 1)


class TestConfidence:
    def test_degenerate_confidence_is_not_calibratable(self):
        """A model that always says 95 has no measurable calibration. The code
        must say so rather than emit a meaningless ECE."""
        recs = [make(True, True, conf_f=95), make(False, False, conf_f=95),
                make(True, True, conf_f=95)]
        s = confidence_summary(recs)
        assert s["calibration_measurable"] is False
        assert s["n_distinct"] == 1
        assert expected_calibration_error(recs) is None

    def test_measurable_when_confidence_varies(self):
        recs = [make(True, True, conf_f=90), make(False, False, conf_f=40),
                make(True, True, conf_f=70), make(False, False, conf_f=20)]
        s = confidence_summary(recs)
        assert s["calibration_measurable"] is True
        ece = expected_calibration_error(recs)
        assert ece is not None and 0.0 <= ece <= 1.0

    def test_overconfidence_gap_sign(self):
        # mean confidence 0.9, accuracy 0.5 -> gap +0.4
        recs = [make(True, True, conf_f=90), make(False, False, conf_f=90)]
        s = confidence_summary(recs)
        assert s["overconfidence_gap"] == pytest.approx(0.4)

    def test_empty_input(self):
        assert confidence_summary([])["calibration_measurable"] is False
