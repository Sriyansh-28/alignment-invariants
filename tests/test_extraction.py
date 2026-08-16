"""Answer parsing. The critical property under test is that an unparseable
reply is never silently graded as a wrong answer."""

from __future__ import annotations

import pytest

from src.evaluation.extract import is_correct, parse_response
from src.tasks.generators import normalize_answer


class TestNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("7", "7"), (" 7 ", "7"), ("07", "7"), ("7.0", "7"), ("+7", "7"),
        ("1,234", "1234"), ("$42", "42"), ("**7**", "7"), ("7.", "7"),
        ("Kestrel", "kestrel"), ("`kestrel`", "kestrel"), ("kestrel.", "kestrel"),
        ("−5", "-5"),
    ])
    def test_normalizes(self, raw, expected):
        assert normalize_answer(raw) == expected


class TestParsing:
    def test_basic(self):
        p = parse_response("Some reasoning.\nFINAL: 42\nCONFIDENCE: 90")
        assert p.answer == "42" and p.confidence == 90 and p.parsed

    def test_markdown_emphasis(self):
        p = parse_response("**FINAL:** **kestrel**\n**CONFIDENCE:** 75")
        assert p.answer == "kestrel" and p.confidence == 75

    def test_assessment_captured(self):
        p = parse_response("ASSESSMENT: INCORRECT\nFINAL: 9\nCONFIDENCE: 60")
        assert p.assessment == "incorrect"
        assert p.claims_previous_wrong is True

    def test_assessment_correct(self):
        p = parse_response("ASSESSMENT: CORRECT\nFINAL: 9\nCONFIDENCE: 60")
        assert p.assessment == "correct"
        assert p.claims_previous_wrong is False

    def test_last_final_wins(self):
        """Models sometimes show an interim answer before settling."""
        p = parse_response("FINAL: 10\nwait, recomputing\nFINAL: 12\nCONFIDENCE: 55")
        assert p.answer == "12"

    def test_final_answer_variant(self):
        p = parse_response("Final answer: 33\nCONFIDENCE: 80")
        assert p.answer == "33"

    def test_prose_on_final_line_takes_trailing_token(self):
        p = parse_response("FINAL: the answer is 17\nCONFIDENCE: 40")
        assert p.answer == "17"

    def test_missing_final_is_unparsed_not_wrong(self):
        p = parse_response("I am not sure how to answer this one.")
        assert p.parsed is False and p.answer is None

    def test_empty_response(self):
        p = parse_response("")
        assert p.parsed is False and p.confidence is None

    def test_template_echo_rejected(self):
        p = parse_response("FINAL: <your answer>\nCONFIDENCE: 50")
        assert p.parsed is False

    def test_out_of_range_confidence_dropped(self):
        p = parse_response("FINAL: 5\nCONFIDENCE: 250")
        assert p.answer == "5" and p.confidence is None

    def test_confidence_with_percent(self):
        p = parse_response("FINAL: 5\nCONFIDENCE: 80%")
        assert p.confidence == 80


class TestGrading:
    def test_exact_match(self):
        assert is_correct("42", "42") is True

    def test_normalized_match(self):
        assert is_correct(" 42.0 ", "42") is True
        assert is_correct("Kestrel", "kestrel") is True

    def test_wrong(self):
        assert is_correct("41", "42") is False

    def test_unparsed_returns_none_not_false(self):
        """The whole point: 'no answer' must not enter an accuracy denominator
        as an error, or every correction rate downstream is corrupted."""
        assert is_correct(None, "42") is None
