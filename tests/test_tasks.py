"""Generator invariants: reproducibility, ground-truth validity, and that the
difficulty ladder is actually a ladder."""

from __future__ import annotations

import hashlib
import itertools
import subprocess
import sys

import pytest

from src.tasks.generators import (DIFFICULTY_SPEC, Task, generate_dataset,
                                  normalize_answer)


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
        """Pilot items must never appear in the eval set."""
        pilot = generate_dataset(seed=1, n_per_cell=3, split="pilot")
        ev = generate_dataset(seed=1, n_per_cell=3, split="eval")
        assert not ({t.prompt for t in pilot} & {t.prompt for t in ev})

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
        assert len(tasks) == 3 * 3 * 3
        cells = {(t.family, t.difficulty) for t in tasks}
        assert len(cells) == 9
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


class TestGroundTruth:
    def test_arith_chain_arithmetic_is_correct(self):
        for t in generate_dataset(seed=11, n_per_cell=4, families=("arith_chain",)):
            v = t.params["start"]
            for op in t.params["trace"]:
                k = int(op[1:])
                v = v + k if op[0] == "+" else v - k if op[0] == "-" else v * k
            assert str(v) == t.answer, t.task_id

    def test_logic_order_solution_is_unique(self):
        """Re-solve each instance from the prompt text and confirm exactly one
        ordering satisfies the stated constraints."""
        for t in generate_dataset(seed=12, n_per_cell=3, families=("logic_order",)):
            order = t.params["order"]
            constraints = []
            for line in t.prompt.splitlines():
                if " finished before " in line:
                    a, b = line.rstrip(".").split(" finished before ")
                    constraints.append((a.strip(), b.strip()))
            sols = [p for p in itertools.permutations(order)
                    if all(p.index(a) < p.index(b) for a, b in constraints)]
            assert len(sols) == 1, f"{t.task_id}: {len(sols)} solutions"
            assert sols[0][t.params["position"] - 1] == t.answer

    def test_set_filter_count_is_correct(self):
        for t in generate_dataset(seed=13, n_per_cell=4, families=("set_filter",)):
            n_rec = t.params["n_records"]
            count = int(t.answer)
            assert 1 <= count <= n_rec - 2, f"{t.task_id}: degenerate count {count}"

    def test_set_filter_predicates_recount_from_prompt(self):
        """Independently recount from the rendered table text."""
        for t in generate_dataset(seed=14, n_per_cell=3, families=("set_filter",)):
            records = []
            for line in t.prompt.splitlines():
                if line.startswith("- ") and "color=" in line:
                    attrs = line.split(": ", 1)[1]
                    d = dict(kv.split("=") for kv in attrs.split(", "))
                    records.append(d)
            assert len(records) == t.params["n_records"]
            n = sum(1 for r in records
                    if all((r[f] != v) if neg else (r[f] == v)
                           for f, v, neg in t.params["predicates"]))
            assert str(n) == t.answer, t.task_id


class TestDifficultyLadder:
    def test_spec_is_monotone_in_complexity(self):
        a = DIFFICULTY_SPEC["arith_chain"]
        assert a[1]["n_ops"] < a[2]["n_ops"] < a[3]["n_ops"]
        assert a[1]["n_distractors"] < a[3]["n_distractors"]
        lo = DIFFICULTY_SPEC["logic_order"]
        assert lo[1]["n_entities"] < lo[2]["n_entities"] < lo[3]["n_entities"]
        sf = DIFFICULTY_SPEC["set_filter"]
        assert sf[1]["n_records"] < sf[2]["n_records"] < sf[3]["n_records"]
        assert sf[1]["n_predicates"] < sf[3]["n_predicates"]

    def test_harder_prompts_are_longer(self):
        """A crude but real check that the manipulation changed the stimulus."""
        for fam in ("arith_chain", "logic_order", "set_filter"):
            lens = []
            for d in (1, 2, 3):
                ts = generate_dataset(seed=7, n_per_cell=4, families=(fam,),
                                      difficulties=(d,))
                lens.append(sum(len(t.prompt) for t in ts) / len(ts))
            assert lens[0] < lens[1] < lens[2], f"{fam}: {lens}"

    @pytest.mark.parametrize("difficulty", [1, 2, 3])
    def test_structure_held_constant_across_levels(self, difficulty):
        """The question template must not change with difficulty, or the
        difficulty contrast is confounded with a wording change."""
        ts = generate_dataset(seed=8, n_per_cell=2, families=("logic_order",),
                              difficulties=(difficulty,))
        for t in ts:
            assert "Who finished in position" in t.prompt
            assert "each finishing at a distinct time" in t.prompt
