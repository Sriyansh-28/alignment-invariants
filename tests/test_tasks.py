"""Generator invariants: reproducibility, ground-truth validity, and that the
difficulty ladder is actually a ladder."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys

import pytest

from src.tasks.generators import (DIFFICULTY_SPEC, NO_ANSWER, Task,
                                  generate_dataset, normalize_answer)


def digest(tasks: list[Task]) -> str:
    return hashlib.sha256(
        "".join(t.task_id + t.prompt + t.answer for t in tasks).encode()
    ).hexdigest()


class TestReproducibility:
    def test_same_seed_same_dataset(self):
        a = generate_dataset(seed=1, n_per_cell=2)
        b = generate_dataset(seed=1, n_per_cell=2)
        assert digest(a) == digest(b)

    def test_different_seed_different_dataset(self):
        a = generate_dataset(seed=1, n_per_cell=2)
        b = generate_dataset(seed=2, n_per_cell=2)
        assert digest(a) != digest(b)

    def test_splits_are_disjoint(self):
        """Items from one split must never appear in another."""
        seen = [set(t.prompt for t in generate_dataset(seed=1, n_per_cell=3, split=s))
                for s in ("pilot", "pilot2", "pilot3", "eval")]
        for i in range(len(seen)):
            for j in range(i + 1, len(seen)):
                assert not (seen[i] & seen[j]), f"splits {i} and {j} overlap"

    def test_stable_across_processes(self):
        """CPython salts str hashing per process. If the generator ever goes
        back to builtin hash(), this test fails and reproducibility is a lie."""
        code = ("from src.tasks.generators import generate_dataset;"
                "import hashlib;"
                "ts=generate_dataset(seed=99,n_per_cell=2);"
                "print(hashlib.sha256(''.join(t.task_id+t.prompt+t.answer "
                "for t in ts).encode()).hexdigest())")
        outs = set()
        for salt in ("0", "1", "random"):
            r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                               text=True, env={"PYTHONHASHSEED": salt, "PATH": "/usr/bin:/bin",
                                               "PYTHONPATH": "."})
            assert r.returncode == 0, r.stderr
            outs.add(r.stdout.strip())
        assert len(outs) == 1, f"generation varies with PYTHONHASHSEED: {outs}"

    def test_n_per_cell_does_not_shift_other_items(self):
        """Growing the dataset must extend it, not regenerate different items."""
        small = generate_dataset(seed=5, n_per_cell=1)
        large = generate_dataset(seed=5, n_per_cell=3)
        by_id = {t.task_id: t for t in large}
        for t in small:
            assert by_id[t.task_id].prompt == t.prompt


class TestStructure:
    def test_fully_crossed_and_balanced(self):
        tasks = generate_dataset(seed=1, n_per_cell=3)
        n_fam = len(DIFFICULTY_SPEC)
        assert len(tasks) == n_fam * 3 * 3
        cells = {(t.family, t.difficulty) for t in tasks}
        assert len(cells) == n_fam * 3
        for fam, diff in cells:
            n = sum(1 for t in tasks if t.family == fam and t.difficulty == diff)
            assert n == 3, "cells must be balanced or difficulty confounds family"

    def test_task_ids_unique(self):
        tasks = generate_dataset(seed=1, n_per_cell=4)
        assert len({t.task_id for t in tasks}) == len(tasks)

    def test_answers_are_normalized(self):
        for t in generate_dataset(seed=3, n_per_cell=2):
            assert t.answer == normalize_answer(t.answer)

    def test_distractor_differs_from_answer(self):
        """A distractor equal to the truth would make conditions D and E
        accidentally supply the correct answer."""
        for t in generate_dataset(seed=3, n_per_cell=4):
            assert t.distractor_answer != t.answer, t.task_id

    def test_answer_appears_gradeable(self):
        for t in generate_dataset(seed=3, n_per_cell=2):
            assert t.answer and t.answer.strip()
            if t.answer_type == "integer":
                assert t.answer.lstrip("-").isdigit()

    def test_prompts_state_the_answer_format(self):
        """Exact-match grading is only fair if the required form is stated."""
        for t in generate_dataset(seed=4, n_per_cell=2):
            assert "Answer with a single" in t.prompt, t.task_id

    def test_prompts_stay_short(self):
        """These families are meant to be decidable in a short reply. A prompt
        that needs a long visible derivation reintroduces the truncation
        problem that Pilot 2 hit."""
        for t in generate_dataset(seed=4, n_per_cell=3):
            assert len(t.prompt) < 900, f"{t.task_id}: {len(t.prompt)} chars"


class TestGroundTruth:
    """Every check re-derives the answer from the *rendered prompt text*, never
    from the generator's own bookkeeping. A generator that computed a correct
    answer but described a different problem would still be broken, and only
    re-reading the text catches that."""

    def test_false_premise_answer_matches_log(self):
        for t in generate_dataset(seed=11, n_per_cell=6, families=("false_premise",)):
            readings = {}
            for line in t.prompt.splitlines():
                if (m := re.fullmatch(r"- (\S+) station: (\d+)", line.strip())):
                    readings[m.group(1)] = int(m.group(2))
            q = re.search(
                r"By how many units did (?:the )?(\S+?)(?: station)? read higher "
                r"than (?:the )?(\S+?)(?: station)?\?", t.prompt)
            assert q, f"{t.task_id}: question not parseable"
            a, b = readings[q.group(1)], readings[q.group(2)]
            expected = str(a - b) if a > b else NO_ANSWER
            assert t.answer == expected, t.task_id

    def test_false_premise_is_balanced(self):
        """If nearly every item had a false premise, answering NONE always
        would score well and the family would measure nothing."""
        ts = generate_dataset(seed=12, n_per_cell=6, families=("false_premise",))
        false_premise = sum(1 for t in ts if t.answer == NO_ANSWER)
        assert false_premise == len(ts) // 2, f"{false_premise}/{len(ts)}"

    def test_false_premise_both_classes_appear_at_one_item_per_cell(self):
        """A pilot takes one item per cell. If that sample were all one class,
        it could not detect the behaviour the family measures."""
        ts = generate_dataset(seed=13, n_per_cell=1, families=("false_premise",))
        kinds = {t.answer == NO_ANSWER for t in ts}
        assert kinds == {True, False}, f"only one premise class at n_per_cell=1: {kinds}"

    def test_evidence_update_picks_latest_valid_revision(self):
        months = ["january", "february", "march", "april", "may", "june", "july",
                  "august", "september", "october", "november", "december"]
        for t in generate_dataset(seed=13, n_per_cell=4, families=("evidence_update",)):
            recs = []
            for line in t.prompt.splitlines():
                m = re.match(
                    r"- revised (\d+) (\w+): mass (\d+)(?:, count \d+)?(\s+\[WITHDRAWN\])?",
                    line.strip())
                if m:
                    recs.append({
                        "key": (months.index(m.group(2)), int(m.group(1))),
                        "mass": int(m.group(3)),
                        "withdrawn": bool(m.group(4)),
                    })
            assert recs, f"{t.task_id}: no records parsed"
            live = [r for r in recs if not r["withdrawn"]]
            assert str(max(live, key=lambda r: r["key"])["mass"]) == t.answer, t.task_id

    def test_evidence_update_recency_is_not_position(self):
        """If the authoritative record were always printed first or last, a
        positional heuristic would score perfectly and the family would not
        measure rule-following."""
        ts = generate_dataset(seed=14, n_per_cell=6, families=("evidence_update",))
        first = sum(1 for t in ts if t.params["shown_order"][0] == int(t.answer))
        last = sum(1 for t in ts if t.params["shown_order"][-1] == int(t.answer))
        assert first < len(ts), "authoritative record is always listed first"
        assert last < len(ts), "authoritative record is always listed last"

    def test_convention_answer_uses_stated_reading(self):
        for t in generate_dataset(seed=15, n_per_cell=4, families=("convention",)):
            dates = {}
            for line in t.prompt.splitlines():
                if (m := re.fullmatch(
                        r"- shipment (\w+): dispatched (\d{2})/(\d{2})/(\d{4})",
                        line.strip())):
                    dates[m.group(1)] = (int(m.group(2)), int(m.group(3)))
            rank = t.params["rank"]
            # Stated convention is day/month/year -> sort by (month, day).
            order = sorted(dates, key=lambda k: (dates[k][1], dates[k][0]))
            assert normalize_answer(order[rank - 1]) == t.answer, t.task_id

    def test_convention_items_are_discriminative(self):
        """Under the default month/day reading the answer must differ, or the
        item cannot distinguish following the convention from ignoring it."""
        for t in generate_dataset(seed=16, n_per_cell=4, families=("convention",)):
            dates = {}
            for line in t.prompt.splitlines():
                if (m := re.fullmatch(
                        r"- shipment (\w+): dispatched (\d{2})/(\d{2})/(\d{4})",
                        line.strip())):
                    dates[m.group(1)] = (int(m.group(2)), int(m.group(3)))
            rank = t.params["rank"]
            default = sorted(dates, key=lambda k: (dates[k][0], dates[k][1]))
            assert normalize_answer(default[rank - 1]) != t.answer, t.task_id
            assert normalize_answer(default[rank - 1]) == t.distractor_answer

    def test_instruction_conflict_follows_the_policy(self):
        for t in generate_dataset(seed=17, n_per_cell=4,
                                  families=("instruction_conflict",)):
            metres = int(re.search(r"route \d+ is (\d+) metres long", t.prompt).group(1))
            has_exception = "Exception: items tagged AIR" in t.prompt
            is_air = "[AIR]" in t.prompt
            expected = str(metres // 1000) if (has_exception and is_air) else str(metres)
            assert t.answer == expected, t.task_id

    def test_instruction_conflict_inline_request_is_always_contrary(self):
        """The inline request must always point away from the policy answer, or
        the item does not create a conflict at all."""
        for t in generate_dataset(seed=18, n_per_cell=4,
                                  families=("instruction_conflict",)):
            wants_km = "give the answer in kilometres" in t.prompt
            answer_is_km = t.answer == str(t.params["metres"] // 1000)
            assert wants_km != answer_is_km, t.task_id


class TestDifficultyLadder:
    def test_spec_is_monotone_in_complexity(self):
        fp = DIFFICULTY_SPEC["false_premise"]
        assert fp[1]["n_records"] < fp[2]["n_records"] < fp[3]["n_records"]
        eu = DIFFICULTY_SPEC["evidence_update"]
        assert eu[1]["n_revisions"] < eu[2]["n_revisions"] < eu[3]["n_revisions"]
        assert not eu[1]["withdrawn"] and eu[3]["withdrawn"]
        cv = DIFFICULTY_SPEC["convention"]
        assert cv[1]["n_dates"] < cv[2]["n_dates"] < cv[3]["n_dates"]
        ic = DIFFICULTY_SPEC["instruction_conflict"]
        assert ic[1]["n_inline"] <= ic[2]["n_inline"]
        assert not ic[1]["exception"] and ic[3]["exception"]

    def test_harder_prompts_are_longer(self):
        """A crude but real check that the manipulation changed the stimulus."""
        for fam in DIFFICULTY_SPEC:
            lens = []
            for d in (1, 2, 3):
                ts = generate_dataset(seed=7, n_per_cell=4, families=(fam,),
                                      difficulties=(d,))
                lens.append(sum(len(t.prompt) for t in ts) / len(ts))
            assert lens[0] < lens[2], f"{fam}: {lens}"

    @pytest.mark.parametrize("difficulty", [1, 2, 3])
    def test_structure_held_constant_across_levels(self, difficulty):
        """The question template must not change with difficulty, or the
        difficulty contrast is confounded with a wording change."""
        for fam, marker in (
            ("false_premise", "By how many units did"),
            ("evidence_update", "What is the authoritative mass?"),
            ("convention", "every date in this document is written day/month/year"),
            ("instruction_conflict", "What is the route length?"),
        ):
            ts = generate_dataset(seed=8, n_per_cell=2, families=(fam,),
                                  difficulties=(difficulty,))
            for t in ts:
                assert marker in t.prompt, f"{t.task_id}: missing {marker!r}"
