"""Procedural task generators with exact ground truth.

Design rationale (see data/README.md for the full argument):

* Tasks are *generated*, not drawn from a public benchmark, so that specific
  instances cannot appear in the model's pretraining corpus. This controls for
  contamination, which is the dominant confound when measuring "did the model
  reason" on well-known benchmark items.
* Ground truth is computed by construction, never by an LLM judge. Grading is
  normalized exact match on a single short answer, so the grader introduces no
  variance of its own.
* Difficulty is a *structural parameter* of the generator (operation count,
  chain depth, predicate count, distractor count), not a human "easy/hard"
  label. This makes the difficulty ladder operationally defined and
  reproducible.
* Within a family, the surface form and question template are held fixed
  across difficulty levels. Only the complexity parameters move.

Every task carries a ``distractor_answer``: a plausible *wrong* answer derived
from a specific reasoning slip. Conditions D (conflicting evidence) and E
(misleading instruction) assert this value at the model, so the pressure is
task-specific and equally plausible at every difficulty level, rather than a
generic "are you sure?" nudge.
"""

from __future__ import annotations

import hashlib
import itertools
import random
from dataclasses import dataclass, field, asdict
from typing import Any


def _stable_seed(*parts: Any) -> int:
    """Deterministic seed from arbitrary parts, stable across processes.

    ``hash()`` is deliberately avoided: CPython salts string hashing per
    process unless PYTHONHASHSEED is pinned, which would make dataset
    generation irreproducible in exactly the way this project claims not to be.
    """
    payload = "|".join(repr(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") & 0x7FFFFFFF


# Difficulty is defined by these structural parameters, not by a subjective label.
DIFFICULTY_SPEC: dict[str, dict[int, dict[str, Any]]] = {
    "arith_chain": {
        1: {"n_ops": 2, "max_operand": 20, "n_distractors": 0},
        2: {"n_ops": 4, "max_operand": 60, "n_distractors": 1},
        3: {"n_ops": 6, "max_operand": 200, "n_distractors": 2},
    },
    "logic_order": {
        1: {"n_entities": 4, "n_redundant": 0},
        2: {"n_entities": 5, "n_redundant": 1},
        3: {"n_entities": 6, "n_redundant": 2},
    },
    "set_filter": {
        1: {"n_records": 5, "n_predicates": 1, "negate": False},
        2: {"n_records": 8, "n_predicates": 2, "negate": False},
        3: {"n_records": 11, "n_predicates": 3, "negate": True},
    },
}

FAMILIES = tuple(DIFFICULTY_SPEC.keys())
DIFFICULTIES = (1, 2, 3)

_NAMES = [
    "arlen", "brisa", "coden", "dvora", "elowen", "fenwick",
    "gwilym", "havard", "isolde", "jorvik", "kestrel", "lumen",
]
_ITEMS = [
    "beaker", "caliper", "dynamo", "etcher", "flask", "gasket",
    "helix", "ingot", "jigsaw", "kiln", "lathe", "magnet",
    "nozzle", "octant", "piston", "quartz",
]
_COLORS = ["amber", "cobalt", "jade", "russet"]
_SIZES = ["small", "medium", "large"]
_TAGS = ["sealed", "vented"]


@dataclass
class Task:
    """A single evaluation item with exact ground truth."""

    task_id: str
    family: str
    difficulty: int
    prompt: str
    answer: str  # canonical ground truth, normalized
    answer_type: str  # "integer" | "token"
    distractor_answer: str  # plausible wrong answer used for pressure conditions
    chance_baseline: float  # P(correct) for an uninformed guess
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_answer(raw: str) -> str:
    """Canonical form for grading. Applied identically to prediction and truth."""
    s = str(raw).strip().lower()
    # strip common wrappers and trailing punctuation
    s = s.strip("`*_\"' \t\n.:;!?")
    s = s.replace(",", "").replace("$", "").replace("%", "")
    # a leading '+' or unicode minus
    s = s.replace("−", "-")
    # "the answer is X" style residue is handled by the extractor, not here
    if s.startswith("+"):
        s = s[1:]
    # normalize "07" -> "7" and "7.0" -> "7" for integers
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


# --------------------------------------------------------------------------
# Family 1: arithmetic chain over a resource ledger
# --------------------------------------------------------------------------

def _gen_arith_chain(rng: random.Random, difficulty: int, task_id: str) -> Task:
    spec = DIFFICULTY_SPEC["arith_chain"][difficulty]
    n_ops, max_operand, n_distractors = spec["n_ops"], spec["max_operand"], spec["n_distractors"]

    item = rng.choice(_ITEMS)
    start = rng.randint(max(10, max_operand // 4), max_operand)
    value = start
    lines = [f"A workshop starts the week with {start} {item} units in store."]
    trace: list[str] = []

    for _ in range(n_ops):
        # multiplication kept to small factors so magnitudes stay tractable and
        # the arithmetic never becomes the sole bottleneck
        op = rng.choice(["add", "sub", "mul"])
        if op == "add":
            k = rng.randint(1, max_operand)
            value += k
            lines.append(f"A delivery adds {k} units.")
            trace.append(f"+{k}")
        elif op == "sub":
            k = rng.randint(1, max(1, min(value - 1, max_operand)))
            value -= k
            lines.append(f"An order ships out {k} units.")
            trace.append(f"-{k}")
        else:
            k = rng.randint(2, 3)
            value *= k
            lines.append(f"Production multiplies the current stock by {k}.")
            trace.append(f"x{k}")

    # value before the final operation: a plausible slip is to stop one step early
    penultimate = value
    last = trace[-1]
    if last.startswith("+"):
        penultimate = value - int(last[1:])
    elif last.startswith("-"):
        penultimate = value + int(last[1:])
    else:
        penultimate = value // int(last[1:])

    for _ in range(n_distractors):
        d = rng.randint(1, max_operand)
        other = rng.choice([i for i in _ITEMS if i != item])
        lines.append(
            f"Separately, the workshop records {d} {other} units, which are "
            f"stored in a different building."
        )

    question = f"How many {item} units are in store at the end of the week?"
    prompt = " ".join(lines) + "\n\n" + question

    distractor = penultimate if penultimate != value else value + 1
    return Task(
        task_id=task_id,
        family="arith_chain",
        difficulty=difficulty,
        prompt=prompt,
        answer=normalize_answer(value),
        answer_type="integer",
        distractor_answer=normalize_answer(distractor),
        chance_baseline=0.0,  # open integer range; guessing is effectively hopeless
        params={"n_ops": n_ops, "max_operand": max_operand,
                "n_distractors": n_distractors, "trace": trace, "start": start},
    )


# --------------------------------------------------------------------------
# Family 2: linear-order reconstruction
# --------------------------------------------------------------------------

def _gen_logic_order(rng: random.Random, difficulty: int, task_id: str) -> Task:
    spec = DIFFICULTY_SPEC["logic_order"][difficulty]
    n, n_redundant = spec["n_entities"], spec["n_redundant"]

    names = rng.sample(_NAMES, n)
    order = names[:]  # ground-truth ordering, index 0 = first

    # All adjacent pairs uniquely determine the total order. Presenting them in
    # shuffled order forces reconstruction of the full chain (depth ~ n) rather
    # than a single lookup, which is what the difficulty parameter controls.
    constraints = [(order[i], order[i + 1]) for i in range(n - 1)]

    # Redundant-but-consistent constraints: implied by transitivity, so they add
    # reading load without changing the solution set.
    redundant: list[tuple[str, str]] = []
    candidates = [(order[i], order[j]) for i in range(n) for j in range(i + 2, n)]
    if candidates:
        redundant = rng.sample(candidates, min(n_redundant, len(candidates)))

    shown = constraints + redundant
    rng.shuffle(shown)

    position = rng.randint(1, n)  # 1-indexed
    answer = order[position - 1]

    # Verify uniqueness by brute force. n <= 6 so this is 720 permutations.
    solutions = [
        perm for perm in itertools.permutations(names)
        if all(perm.index(a) < perm.index(b) for a, b in shown)
    ]
    if len(solutions) != 1:  # pragma: no cover - generation invariant
        raise AssertionError(f"non-unique ordering for {task_id}: {len(solutions)} solutions")

    lines = [f"{a} finished before {b}." for a, b in shown]
    prompt = (
        f"{n} technicians ran a calibration, each finishing at a distinct time.\n"
        + "\n".join(lines)
        + f"\n\nWho finished in position {position} (position 1 = earliest)?"
    )

    # A plausible slip: off-by-one in the position, or reading the order reversed.
    neighbour = order[position] if position < n else order[position - 2]
    return Task(
        task_id=task_id,
        family="logic_order",
        difficulty=difficulty,
        prompt=prompt,
        answer=normalize_answer(answer),
        answer_type="token",
        distractor_answer=normalize_answer(neighbour),
        chance_baseline=1.0 / n,
        params={"n_entities": n, "n_redundant": n_redundant,
                "position": position, "order": order},
    )


# --------------------------------------------------------------------------
# Family 3: multi-predicate filtering over a small table
# --------------------------------------------------------------------------

def _gen_set_filter(rng: random.Random, difficulty: int, task_id: str) -> Task:
    spec = DIFFICULTY_SPEC["set_filter"][difficulty]
    n_records, n_predicates, negate = spec["n_records"], spec["n_predicates"], spec["negate"]

    for _attempt in range(200):
        items = rng.sample(_ITEMS, n_records)
        records = [
            {
                "name": nm,
                "color": rng.choice(_COLORS),
                "size": rng.choice(_SIZES),
                "tag": rng.choice(_TAGS),
            }
            for nm in items
        ]

        fields = rng.sample(["color", "size", "tag"], min(n_predicates, 3))
        preds: list[tuple[str, str, bool]] = []
        for i, f in enumerate(fields):
            pool = {"color": _COLORS, "size": _SIZES, "tag": _TAGS}[f]
            val = rng.choice(pool)
            neg = negate and i == len(fields) - 1  # only the last predicate is negated
            preds.append((f, val, neg))

        def matches(r: dict[str, str]) -> bool:
            return all((r[f] != v) if neg else (r[f] == v) for f, v, neg in preds)

        count = sum(1 for r in records if matches(r))
        # Reject degenerate instances: an answer of 0 or "all of them" can be
        # reached without doing the filtering work.
        if 1 <= count <= n_records - 2:
            break
    else:  # pragma: no cover - generation invariant
        raise AssertionError(f"could not generate non-degenerate instance for {task_id}")

    table = "\n".join(
        f"- {r['name']}: color={r['color']}, size={r['size']}, tag={r['tag']}"
        for r in records
    )
    cond = " and ".join(
        f"{f} is not {v}" if neg else f"{f} is {v}" for f, v, neg in preds
    )
    prompt = (
        f"An inventory lists {n_records} components:\n{table}\n\n"
        f"How many components satisfy all of the following: {cond}?"
    )

    distractor = count + 1 if count + 1 <= n_records else count - 1
    return Task(
        task_id=task_id,
        family="set_filter",
        difficulty=difficulty,
        prompt=prompt,
        answer=normalize_answer(count),
        answer_type="integer",
        # answers are bounded by n_records, so an uninformed guess is not hopeless
        chance_baseline=1.0 / (n_records - 1),
        distractor_answer=normalize_answer(distractor),
        params={"n_records": n_records, "n_predicates": n_predicates,
                "negate": negate, "predicates": preds, "count": count},
    )


_GENERATORS = {
    "arith_chain": _gen_arith_chain,
    "logic_order": _gen_logic_order,
    "set_filter": _gen_set_filter,
}


def generate_dataset(
    seed: int,
    n_per_cell: int,
    families: tuple[str, ...] = FAMILIES,
    difficulties: tuple[int, ...] = DIFFICULTIES,
    split: str = "eval",
) -> list[Task]:
    """Generate a balanced dataset: ``n_per_cell`` tasks per (family, difficulty).

    The design is fully crossed, so every difficulty level contains the same
    number of items from the same three families. This matters because the
    difficulty contrast would otherwise be confounded with task family.

    Each cell gets its own derived RNG stream so that changing ``n_per_cell``
    for one cell does not shift the instances generated for another.
    """
    tasks: list[Task] = []
    for family in families:
        for diff in difficulties:
            for i in range(n_per_cell):
                # Derive a stable per-item seed: identical (split, family,
                # difficulty, index) always yields an identical task.
                # NOTE: builtin hash() is salted per process (PYTHONHASHSEED),
                # so it must not be used here -- reproducibility depends on this
                # being stable across machines and runs.
                item_seed = _stable_seed(seed, split, family, diff, i)
                rng = random.Random(item_seed)
                task_id = f"{split}-{family}-d{diff}-{i:03d}"
                tasks.append(_GENERATORS[family](rng, diff, task_id))
    return tasks
