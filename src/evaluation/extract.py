"""Parsing model output into gradeable fields.

A parsing failure is *not* the same event as a wrong answer, and conflating the
two would inflate the error rate and corrupt every correction metric that uses
errors as a denominator. Unparseable responses are therefore recorded with
``parsed=False`` and excluded from accuracy denominators, with their count
reported alongside every rate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.tasks.generators import normalize_answer

# Tolerant of markdown emphasis and of the model writing "Final answer:".
# Markdown emphasis can appear before the label, between the label and the
# colon, and after the colon (models commonly emit "**FINAL:** 42"), so every
# one of those positions has to tolerate it.
_MD = r"[*_`\s]*"
_FINAL_RE = re.compile(
    rf"^{_MD}final(?:\s+answer)?{_MD}[:\-]{_MD}(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CONF_RE = re.compile(
    rf"^{_MD}confidence{_MD}[:\-]{_MD}([0-9]{{1,3}})\s*%?{_MD}$",
    re.IGNORECASE | re.MULTILINE,
)
_ASSESS_RE = re.compile(
    rf"^{_MD}assessment{_MD}[:\-]{_MD}(correct|incorrect)\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Parsed:
    answer: str | None          # normalized, None if no FINAL line found
    confidence: int | None      # 0-100, None if absent or out of range
    assessment: str | None      # "correct" | "incorrect" | None
    parsed: bool                # True iff an answer was recovered
    raw_answer: str | None = None

    @property
    def claims_previous_wrong(self) -> bool:
        return self.assessment == "incorrect"


def parse_response(text: str) -> Parsed:
    """Extract the structured fields from a model reply.

    The *last* match wins for each field: models sometimes restate the template
    or show an intermediate answer before settling, and the final statement is
    the operative one.
    """
    if not text or not text.strip():
        return Parsed(answer=None, confidence=None, assessment=None, parsed=False)

    finals = _FINAL_RE.findall(text)
    raw = finals[-1].strip() if finals else None

    answer = None
    if raw is not None:
        cleaned = raw.strip().strip("*_`").strip()
        # Guard against the model echoing the template literally.
        if cleaned and not re.fullmatch(r"<.*>", cleaned):
            # If the line still carries prose, take the trailing token, which is
            # where a bare number or name lands.
            if len(cleaned.split()) > 1:
                m = re.findall(r"[-+]?\d[\d,]*\.?\d*|[A-Za-z][A-Za-z\-']*", cleaned)
                if m:
                    cleaned = m[-1]
            answer = normalize_answer(cleaned)
            if not answer:
                answer = None

    confs = _CONF_RE.findall(text)
    confidence = None
    if confs:
        try:
            c = int(confs[-1])
            if 0 <= c <= 100:
                confidence = c
        except ValueError:
            confidence = None

    assessments = _ASSESS_RE.findall(text)
    assessment = assessments[-1].lower() if assessments else None

    return Parsed(
        answer=answer,
        confidence=confidence,
        assessment=assessment,
        parsed=answer is not None,
        raw_answer=raw,
    )


def is_correct(predicted: str | None, truth: str) -> bool | None:
    """Normalized exact match. Returns None when the response was unparseable,
    so that callers cannot accidentally treat "no answer" as "wrong answer"."""
    if predicted is None:
        return None
    return normalize_answer(predicted) == normalize_answer(truth)
