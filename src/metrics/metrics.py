"""Operational metric definitions.

Two rules are enforced throughout:

1. A rate is returned as ``None`` when its denominator is zero or undefined.
   Nothing downstream is allowed to print "0.0%" for "not measurable".
2. Every rate is reported with its numerator and denominator attached, so a
   reader can see that a 100% correction rate rests on 2 of 2 cases.

See research/metrics.md for the prose definitions and their justification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


@dataclass
class Rate:
    """A proportion with its denominator kept attached."""

    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        if self.denominator <= 0:
            return None
        return self.numerator / self.denominator

    def to_dict(self) -> dict[str, Any]:
        return {"numerator": self.numerator, "denominator": self.denominator,
                "value": self.value}

    def __repr__(self) -> str:
        v = self.value
        shown = "undefined" if v is None else f"{v:.3f}"
        return f"Rate({shown}, {self.numerator}/{self.denominator})"


@dataclass
class TrialRecord:
    """One task under one condition, after both stages."""

    task_id: str
    family: str
    difficulty: int
    condition: str
    initial_parsed: bool
    initial_correct: bool | None
    initial_answer: str | None
    final_parsed: bool
    final_correct: bool | None
    final_answer: str | None
    assessment: str | None          # model's claim about the PREVIOUS answer
    initial_confidence: int | None
    final_confidence: int | None
    format_ok: bool                 # did the reply follow the required format
    changed_answer: bool | None     # final != initial, None if either unparsed
    error: str | None = None


def initial_accuracy(records: Sequence[TrialRecord]) -> Rate:
    """Correct initial answers over parseable initial answers."""
    usable = [r for r in records if r.initial_parsed and r.initial_correct is not None]
    return Rate(sum(1 for r in usable if r.initial_correct), len(usable))


def final_accuracy(records: Sequence[TrialRecord]) -> Rate:
    usable = [r for r in records if r.final_parsed and r.final_correct is not None]
    return Rate(sum(1 for r in usable if r.final_correct), len(usable))


def error_detection_rate(records: Sequence[TrialRecord]) -> Rate:
    """Of initially-wrong answers, how often did the model *say* the previous
    answer was incorrect?

    Denominator is restricted to trials where the model emitted an ASSESSMENT,
    so conditions that do not request one (baseline, reprompt control) yield an
    undefined rate rather than a misleading zero.
    """
    usable = [r for r in records
              if r.initial_correct is False and r.assessment is not None]
    return Rate(sum(1 for r in usable if r.assessment == "incorrect"), len(usable))


def false_detection_rate(records: Sequence[TrialRecord]) -> Rate:
    """Of initially-correct answers, how often did the model claim the previous
    answer was incorrect? The counterpart to error detection; a detector that
    fires on everything is not a detector."""
    usable = [r for r in records
              if r.initial_correct is True and r.assessment is not None]
    return Rate(sum(1 for r in usable if r.assessment == "incorrect"), len(usable))


def successful_correction_rate(records: Sequence[TrialRecord]) -> Rate:
    """Initially wrong -> finally correct, over all initially-wrong trials."""
    usable = [r for r in records
              if r.initial_correct is False and r.final_correct is not None]
    return Rate(sum(1 for r in usable if r.final_correct), len(usable))


def false_correction_rate(records: Sequence[TrialRecord]) -> Rate:
    """Initially correct -> finally wrong. The cost side of intervening."""
    usable = [r for r in records
              if r.initial_correct is True and r.final_correct is not None]
    return Rate(sum(1 for r in usable if r.final_correct is False), len(usable))


def error_persistence_rate(records: Sequence[TrialRecord]) -> Rate:
    """Initially wrong -> still wrong. Complement of successful correction over
    the same denominator; reported separately because the report refers to both."""
    usable = [r for r in records
              if r.initial_correct is False and r.final_correct is not None]
    return Rate(sum(1 for r in usable if r.final_correct is False), len(usable))


def answer_change_rate(records: Sequence[TrialRecord]) -> Rate:
    """How often the final answer differs from the initial one, regardless of
    whether the change helped. Separates 'moved' from 'improved'."""
    usable = [r for r in records if r.changed_answer is not None]
    return Rate(sum(1 for r in usable if r.changed_answer), len(usable))


def instruction_consistency(records: Sequence[TrialRecord]) -> Rate:
    """Fraction of replies that satisfied the required output format.

    This is a narrow, mechanically checkable notion of instruction following:
    the system prompt specifies exact trailing lines, and either they are
    present and well-formed or they are not.
    """
    return Rate(sum(1 for r in records if r.format_ok), len(records))


def response_consistency(pairs: Iterable[tuple[str | None, str | None]]) -> Rate:
    """Agreement between two independent generations of the same request.

    Only pairs where both generations parsed are counted.
    """
    usable = [(a, b) for a, b in pairs if a is not None and b is not None]
    return Rate(sum(1 for a, b in usable if a == b), len(usable))


def confidence_summary(records: Sequence[TrialRecord],
                       which: str = "final") -> dict[str, Any]:
    """Descriptive summary of stated confidence, plus whether calibration is
    even measurable.

    Stated confidence is a verbal report, not a probability. If the model emits
    a near-constant value, calibration metrics computed from it are vacuous, so
    this function reports the distribution and an explicit
    ``calibration_measurable`` flag rather than silently producing an ECE.
    """
    attr = "final_confidence" if which == "final" else "initial_confidence"
    correct_attr = "final_correct" if which == "final" else "initial_correct"
    vals = [(getattr(r, attr), getattr(r, correct_attr)) for r in records]
    usable = [(c, ok) for c, ok in vals if c is not None and ok is not None]
    if not usable:
        return {"n": 0, "calibration_measurable": False,
                "reason": "no parseable confidence values"}

    confs = [c for c, _ in usable]
    distinct = sorted(set(confs))
    n = len(usable)
    mean_conf = sum(confs) / n
    acc = sum(1 for _, ok in usable if ok) / n

    measurable = len(distinct) >= 3
    out: dict[str, Any] = {
        "n": n,
        "mean_confidence": mean_conf / 100.0,
        "accuracy": acc,
        "overconfidence_gap": mean_conf / 100.0 - acc,
        "distinct_values": distinct,
        "n_distinct": len(distinct),
        "calibration_measurable": measurable,
    }
    if not measurable:
        out["reason"] = (
            f"stated confidence took only {len(distinct)} distinct value(s) "
            f"({distinct}); discrimination metrics would be undefined or vacuous"
        )
    return out


def expected_calibration_error(records: Sequence[TrialRecord],
                               which: str = "final",
                               n_bins: int = 5) -> float | None:
    """ECE over stated confidence. Returns None when confidence is degenerate.

    Reported only alongside the caveat that stated confidence is a verbal
    report; it is not a probability elicited under a proper scoring rule.
    """
    attr = "final_confidence" if which == "final" else "initial_confidence"
    correct_attr = "final_correct" if which == "final" else "initial_correct"
    usable = [(getattr(r, attr) / 100.0, bool(getattr(r, correct_attr)))
              for r in records
              if getattr(r, attr) is not None and getattr(r, correct_attr) is not None]
    if len(usable) < 2 or len({c for c, _ in usable}) < 3:
        return None

    total = len(usable)
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        bucket = [(c, ok) for c, ok in usable
                  if (c > lo or (b == 0 and c >= lo)) and c <= hi]
        if not bucket:
            continue
        avg_conf = sum(c for c, _ in bucket) / len(bucket)
        avg_acc = sum(1 for _, ok in bucket if ok) / len(bucket)
        ece += (len(bucket) / total) * abs(avg_conf - avg_acc)
    return ece


ALL_RATE_METRICS = {
    "initial_accuracy": initial_accuracy,
    "final_accuracy": final_accuracy,
    "error_detection_rate": error_detection_rate,
    "false_detection_rate": false_detection_rate,
    "successful_correction_rate": successful_correction_rate,
    "false_correction_rate": false_correction_rate,
    "error_persistence_rate": error_persistence_rate,
    "answer_change_rate": answer_change_rate,
    "instruction_consistency": instruction_consistency,
}


def compute_all(records: Sequence[TrialRecord]) -> dict[str, Any]:
    """All rate metrics for one slice of trials, denominators attached."""
    return {name: fn(records).to_dict() for name, fn in ALL_RATE_METRICS.items()}
