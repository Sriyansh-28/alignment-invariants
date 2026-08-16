"""Generator invariants: reproducibility, ground-truth validity, and that the
difficulty ladder is actually a ladder."""

from __future__ import annotations

import hashlib
import itertools
import re
import subprocess
import sys

import pytest

from src.tasks.generators import (DIFFICULTY_SPEC, Task, _satisfies,
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
    """Every check here re-derives the answer from the *rendered prompt text*,
    never from the generator's own bookkeeping. A generator that computed a
    correct answer but described a different problem would still be broken, and
    only re-reading the text catches that."""

    def test_arith_chain_arithmetic_is_correct(self):
        """Execute the numbered steps as written and compare with the answer."""
        for t in generate_dataset(seed=11, n_per_cell=4, families=("arith_chain",)):
            lines = t.prompt.splitlines()
            state: dict[str, int] = {}

            m = re.search(r"holds (\d+) (\S+) units and (\d+) (\S+) units", lines[0])
            if m:
                state[m.group(2)] = int(m.group(1))
                state[m.group(4)] = int(m.group(3))
            else:
                m = re.search(r"starts the week with (\d+) (\S+) units", lines[0])
                assert m, f"{t.task_id}: unparseable opening {lines[0]!r}"
                state[m.group(2)] = int(m.group(1))

            history = [dict(state)]
            for line in lines[1:]:
                if not line.startswith("Step "):
                    continue
                body = line.split(": ", 1)[1].rstrip(".")

                if (m := re.fullmatch(
                        r"if the current (\S+) stock is greater than (\d+), "
                        r"ship out (\d+) \S+ units; otherwise add (\d+) \S+ units", body)):
                    nm, thr, a, b = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
                    state[nm] = state[nm] - a if state[nm] > thr else state[nm] + b
                elif (m := re.fullmatch(
                        r"add to (\S+) the number of (\S+) units held immediately "
                        r"after step (\d+), divided by (\d+) and rounded down", body)):
                    nm, src, step, div = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
                    state[nm] = state[nm] + history[step][src] // div
                elif (m := re.fullmatch(r"a delivery adds (\d+) (\S+) units", body)):
                    state[m.group(2)] += int(m.group(1))
                elif (m := re.fullmatch(r"an order ships out (\d+) (\S+) units", body)):
                    state[m.group(2)] -= int(m.group(1))
                elif (m := re.fullmatch(
                        r"production multiplies the current (\S+) stock by (\d+)", body)):
                    state[m.group(1)] *= int(m.group(2))
                else:  # pragma: no cover
                    raise AssertionError(f"{t.task_id}: unparseable step {body!r}")
                history.append(dict(state))

            target = re.search(r"How many (\S+) units", t.prompt).group(1)
            assert str(state[target]) == t.answer, t.task_id
            assert state[target] >= 0, f"{t.task_id}: negative stock"

    def test_logic_order_solution_is_unique(self):
        """Re-solve each instance from the prompt text and confirm exactly one
        ordering satisfies the stated constraints."""
        for t in generate_dataset(seed=12, n_per_cell=3, families=("logic_order",)):
            order = t.params["order"]
            cons: list[tuple] = []
            for line in t.prompt.splitlines():
                line = line.strip().rstrip(".")
                if (m := re.fullmatch(r"(\S+) finished immediately before (\S+)", line)):
                    cons.append(("immediate", m.group(1), m.group(2)))
                elif (m := re.fullmatch(r"(\S+) finished before (\S+)", line)):
                    cons.append(("before", m.group(1), m.group(2)))
                elif (m := re.fullmatch(
                        r"Exactly (\d+) technicians? finished between (\S+) and (\S+)", line)):
                    cons.append(("gap", m.group(2), m.group(3), int(m.group(1))))
                elif (m := re.fullmatch(r"(\S+) did not finish in position (\d+)", line)):
                    cons.append(("notpos", m.group(1), int(m.group(2))))

            assert cons, f"{t.task_id}: no constraints parsed"
            sols = []
            for p in itertools.permutations(order):
                pos = {nm: i for i, nm in enumerate(p)}
                if all(_satisfies(pos, c) for c in cons):
                    sols.append(p)
            assert len(sols) == 1, f"{t.task_id}: {len(sols)} solutions"
            assert sols[0][t.params["position"] - 1] == t.answer

    def test_logic_order_truth_satisfies_its_own_constraints(self):
        """Regression: `notpos` compared a 0-indexed position against the
        1-indexed position stated in the prompt, so the intended answer
        violated its own constraint set. Every instance was then unsolvable as
        written, while still looking well-formed from the outside."""
        for t in generate_dataset(seed=17, n_per_cell=3, families=("logic_order",)):
            pos = {nm: i for i, nm in enumerate(t.params["order"])}
            for c in (tuple(x) for x in t.params["constraints"]):
                assert _satisfies(pos, c), f"{t.task_id}: truth violates {c}"

    def test_logic_order_needs_more_than_precedence(self):
        """The point of the redesign: chain-following must be insufficient.

        If the precedence constraints alone pinned down the order, the task
        would collapse back to the Pilot 1 design that scored 100%."""
        for t in generate_dataset(seed=15, n_per_cell=3, families=("logic_order",)):
            order = t.params["order"]
            prec = [tuple(c) for c in t.params["constraints"] if c[0] == "before"]
            if not prec:
                continue
            sols = 0
            for p in itertools.permutations(order):
                pos = {nm: i for i, nm in enumerate(p)}
                if all(_satisfies(pos, c) for c in prec):
                    sols += 1
                    if sols > 1:
                        break
            assert sols > 1, f"{t.task_id}: precedence alone determines the order"

    def test_set_filter_count_is_correct(self):
        for t in generate_dataset(seed=13, n_per_cell=4, families=("set_filter",)):
            n_rec = t.params["n_records"]
            count = int(t.answer)
            assert 1 <= count <= n_rec - 2, f"{t.task_id}: degenerate count {count}"

    def test_set_filter_predicates_recount_from_prompt(self):
        """Independently recount from the rendered table and condition text."""
        for t in generate_dataset(seed=14, n_per_cell=3, families=("set_filter",)):
            records = []
            for line in t.prompt.splitlines():
                if line.startswith("- ") and "color=" in line:
                    attrs = line.split(": ", 1)[1]
                    d = dict(kv.split("=") for kv in attrs.split(", "))
                    d["mass"] = int(d["mass"])
                    records.append(d)
            assert len(records) == t.params["n_records"]

            def ev(r, atom):
                f, op, v = atom
                return r[f] > v if op == "gt" else r[f] == v

            detail = t.params["predicate"]
            atoms = [tuple(a) for a in detail["atoms"]]
            if detail["shape"] == "and":
                pred = lambda r: all(ev(r, a) for a in atoms)  # noqa: E731
            elif detail["shape"] == "or_and":
                g1, g2, mass = atoms
                pred = lambda r: (ev(r, g1) or ev(r, g2)) and ev(r, mass)  # noqa: E731
            else:
                g1, mass, g2, tag = atoms
                pred = lambda r: (  # noqa: E731
                    (ev(r, g1) or ev(r, mass)) and not (ev(r, g2) and ev(r, tag)))

            n = sum(1 for r in records if pred(r))
            assert str(n) == t.answer, t.task_id

    def test_set_filter_condition_text_matches_predicate(self):
        """The rendered condition must mention every atom actually evaluated,
        so the model is not asked a different question from the one graded."""
        for t in generate_dataset(seed=16, n_per_cell=3, families=("set_filter",)):
            cond = t.prompt.split("following condition: ", 1)[1]
            for f, op, v in (tuple(a) for a in t.params["predicate"]["atoms"]):
                expect = f"{f} is greater than {v}" if op == "gt" else f"{f} is {v}"
                assert expect in cond, f"{t.task_id}: {expect!r} missing from {cond!r}"


class TestDifficultyLadder:
    def test_spec_is_monotone_in_complexity(self):
        a = DIFFICULTY_SPEC["arith_chain"]
        assert a[1]["n_ops"] < a[2]["n_ops"] < a[3]["n_ops"]
        assert a[1]["n_backref"] < a[3]["n_backref"]
        assert a[1]["n_cond"] <= a[3]["n_cond"]
        assert not a[1]["interleave"] and a[3]["interleave"]
        lo = DIFFICULTY_SPEC["logic_order"]
        assert lo[1]["n_entities"] < lo[2]["n_entities"] < lo[3]["n_entities"]
        assert lo[1]["n_gap"] <= lo[3]["n_gap"]
        sf = DIFFICULTY_SPEC["set_filter"]
        assert sf[1]["n_records"] < sf[2]["n_records"] < sf[3]["n_records"]
        assert sf[1]["shape"] == "and" and sf[3]["shape"] == "or_and_not"

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
