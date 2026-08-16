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
#
# REVISION 2 (see research/hypotheses.md, Addendum 3). Pilot 1 scored 48/48 on
# the original parameters: every cell was at ceiling, so the correction-rate
# denominator was empty and no hypothesis was testable. The diagnosis was that
# each family was solvable by a single forward pass with no state to maintain:
#
#   arith_chain  a straight line of independent add/sub/mul steps, so no
#                intermediate value ever had to be retained or revisited, and
#                the distractor sentences announced their own irrelevance
#                ("stored in a different building").
#   logic_order  the constraint list always contained every adjacent pair of
#                the true order, so the answer could be read off by following a
#                chain. No transitive inference was ever required. This is not
#                incidental: for pure precedence constraints, a unique linear
#                extension exists only if all adjacent pairs are present, so
#                that family cannot be made hard without other constraint types.
#   set_filter   at most 11 rows and a plain conjunction, scannable in one pass.
#
# The revision raises the reasoning depth of each family rather than obscuring
# the questions. Ground truth is still computed by construction, and the surface
# form is still held fixed across levels within a family.
DIFFICULTY_SPEC: dict[str, dict[int, dict[str, Any]]] = {
    # n_ops        length of the ledger
    # interleave   track two component lines at once, so each step must be
    #              bound to the right ledger (interference, not just length)
    # n_cond       steps whose effect depends on the running value at that point
    # n_backref    steps referring to the value held after an earlier step,
    #              which forces intermediate state to be retained
    "arith_chain": {
        1: {"n_ops": 5, "max_operand": 60, "interleave": False, "n_cond": 1, "n_backref": 0},
        2: {"n_ops": 8, "max_operand": 150, "interleave": True, "n_cond": 1, "n_backref": 1},
        3: {"n_ops": 11, "max_operand": 300, "interleave": True, "n_cond": 2, "n_backref": 2},
    },
    # Constraint sets mix precedence with adjacency, gap and negative-position
    # constraints, and are rejected unless the precedence constraints *alone*
    # leave the order ambiguous. That makes chain-following insufficient by
    # construction and forces genuine constraint propagation.
    "logic_order": {
        1: {"n_entities": 5, "n_gap": 1, "n_immediate": 1, "n_negative": 0},
        2: {"n_entities": 6, "n_gap": 1, "n_immediate": 1, "n_negative": 1},
        3: {"n_entities": 7, "n_gap": 2, "n_immediate": 1, "n_negative": 1},
    },
    # A numeric column adds threshold comparisons, and the predicate tree grows
    # from a flat conjunction to a nested boolean with a negated group.
    "set_filter": {
        1: {"n_records": 10, "shape": "and", "numeric": True},
        2: {"n_records": 16, "shape": "or_and", "numeric": True},
        3: {"n_records": 22, "shape": "or_and_not", "numeric": True},
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
    # Extended so the largest set_filter table (22 rows) still draws distinct
    # names. Without these the generator fell back to suffixed duplicates
    # ("nozzle-16"), which read as a different kind of object and added noise
    # to the stimulus for no experimental reason.
    "ratchet", "sleeve", "turbine", "union", "vernier", "washer",
    "yoke", "zener",
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
    """Ledger simulation with interleaving, conditionals and back-references.

    Every step is stated as an explicit numbered instruction over a named
    component line, and the ground truth is the result of executing those
    instructions literally. There is no hidden rule and no wordplay: the
    difficulty comes from the number of steps, from having to bind each step to
    the right line, and from steps whose effect depends on state the solver must
    still be holding (the current value, or the value after an earlier step).
    """
    spec = DIFFICULTY_SPEC["arith_chain"][difficulty]
    n_ops, max_operand = spec["n_ops"], spec["max_operand"]
    interleave, n_cond, n_backref = spec["interleave"], spec["n_cond"], spec["n_backref"]

    if interleave:
        target, other = rng.sample(_ITEMS, 2)
        ledgers = [target, other]
    else:
        target = rng.choice(_ITEMS)
        ledgers = [target]

    state = {name: rng.randint(max(20, max_operand // 4), max_operand) for name in ledgers}
    # history[i][name] = value of `name` immediately after step i (1-indexed)
    history: list[dict[str, int]] = [dict(state)]

    if interleave:
        opening = (
            f"A workshop tracks two component lines. At the start of the week it "
            f"holds {state[ledgers[0]]} {ledgers[0]} units and "
            f"{state[ledgers[1]]} {ledgers[1]} units."
        )
    else:
        opening = (
            f"A workshop starts the week with {state[target]} {target} units in store."
        )

    # Decide which step indices carry the harder step types. Back-references need
    # an earlier step to point at, so they are never placed in the first two.
    idx = list(range(1, n_ops + 1))
    cond_slots = set(rng.sample(idx, min(n_cond, len(idx))))
    backref_pool = [i for i in idx if i >= 3 and i not in cond_slots]
    backref_slots = set(rng.sample(backref_pool, min(n_backref, len(backref_pool))))

    lines: list[str] = []
    trace: list[str] = []

    for step in range(1, n_ops + 1):
        name = rng.choice(ledgers)
        cur = state[name]

        if step in cond_slots:
            # Threshold placed near the current value so both branches are
            # live: the solver cannot shortcut by assuming one branch.
            threshold = max(1, cur + rng.randint(-cur // 3 - 1, cur // 3 + 1))
            a = rng.randint(1, max(1, min(cur - 1, max_operand)))
            b = rng.randint(1, max_operand)
            lines.append(
                f"Step {step}: if the current {name} stock is greater than {threshold}, "
                f"ship out {a} {name} units; otherwise add {b} {name} units."
            )
            if cur > threshold:
                state[name] = cur - a
                trace.append(f"{name}: cond>{threshold} -> -{a}")
            else:
                state[name] = cur + b
                trace.append(f"{name}: cond<={threshold} -> +{b}")

        elif step in backref_slots:
            src_step = rng.randint(1, step - 1)
            src_name = rng.choice(ledgers)
            divisor = rng.choice([2, 3, 4])
            add = history[src_step][src_name] // divisor
            lines.append(
                f"Step {step}: add to {name} the number of {src_name} units held "
                f"immediately after step {src_step}, divided by {divisor} and "
                f"rounded down."
            )
            state[name] = cur + add
            trace.append(f"{name}: backref s{src_step}.{src_name}//{divisor} -> +{add}")

        else:
            op = rng.choice(["add", "sub", "mul"])
            if op == "add":
                k = rng.randint(1, max_operand)
                state[name] = cur + k
                lines.append(f"Step {step}: a delivery adds {k} {name} units.")
                trace.append(f"{name}: +{k}")
            elif op == "sub":
                k = rng.randint(1, max(1, min(cur - 1, max_operand)))
                state[name] = cur - k
                lines.append(f"Step {step}: an order ships out {k} {name} units.")
                trace.append(f"{name}: -{k}")
            else:
                k = rng.randint(2, 3)
                state[name] = cur * k
                lines.append(
                    f"Step {step}: production multiplies the current {name} stock by {k}."
                )
                trace.append(f"{name}: x{k}")

        history.append(dict(state))

    value = state[target]

    # Plausible slip: report the target's value one step before the end. If the
    # final step did not touch the target that value is identical, so fall back
    # to the last step that did move it.
    distractor = value
    for i in range(len(history) - 2, -1, -1):
        if history[i][target] != value:
            distractor = history[i][target]
            break
    if distractor == value:
        distractor = value + 1

    question = f"How many {target} units are in store at the end of the week?"
    prompt = opening + "\n" + "\n".join(lines) + "\n\n" + question

    return Task(
        task_id=task_id,
        family="arith_chain",
        difficulty=difficulty,
        prompt=prompt,
        answer=normalize_answer(value),
        answer_type="integer",
        distractor_answer=normalize_answer(distractor),
        chance_baseline=0.0,  # open integer range; guessing is effectively hopeless
        params={"n_ops": n_ops, "max_operand": max_operand, "interleave": interleave,
                "n_cond": n_cond, "n_backref": n_backref, "trace": trace,
                "target": target, "start": history[0]},
    )


# --------------------------------------------------------------------------
# Family 2: linear-order reconstruction
# --------------------------------------------------------------------------

def _satisfies(pos: dict[str, int], c: tuple) -> bool:
    """Evaluate one constraint against a candidate assignment of positions."""
    kind = c[0]
    if kind == "before":
        return pos[c[1]] < pos[c[2]]
    if kind == "immediate":
        return pos[c[2]] == pos[c[1]] + 1
    if kind == "gap":
        return abs(pos[c[1]] - pos[c[2]]) - 1 == c[3]
    if kind == "notpos":
        # `pos` is 0-indexed; positions are stated to the model 1-indexed.
        return pos[c[1]] != c[2] - 1
    raise ValueError(f"unknown constraint kind: {kind}")  # pragma: no cover


def _render(c: tuple) -> str:
    kind = c[0]
    if kind == "before":
        return f"{c[1]} finished before {c[2]}."
    if kind == "immediate":
        return f"{c[1]} finished immediately before {c[2]}."
    if kind == "gap":
        n_between = c[3]
        word = "technician" if n_between == 1 else "technicians"
        return f"Exactly {n_between} {word} finished between {c[1]} and {c[2]}."
    if kind == "notpos":
        return f"{c[1]} did not finish in position {c[2]}."
    raise ValueError(f"unknown constraint kind: {kind}")  # pragma: no cover


def _count_solutions(names: list[str], constraints: list[tuple], limit: int = 2) -> int:
    """Number of orderings satisfying every constraint, capped at ``limit``."""
    found = 0
    for perm in itertools.permutations(names):
        pos = {nm: i for i, nm in enumerate(perm)}
        if all(_satisfies(pos, c) for c in constraints):
            found += 1
            if found >= limit:
                break
    return found


def _gen_logic_order(rng: random.Random, difficulty: int, task_id: str) -> Task:
    """Order reconstruction from a mixed, deliberately indirect constraint set.

    The previous version listed every adjacent pair of the true order, which
    makes the puzzle a chain walk. That was not a tuning oversight but a
    structural property: a set of pure precedence constraints has a unique
    linear extension only when it contains all adjacent pairs, so the family is
    necessarily easy while precedence is the only constraint type available.

    Adjacency, gap and negative-position constraints break that. Here a task is
    accepted only if the full set has exactly one solution *and* the precedence
    constraints on their own leave the order ambiguous, so the solver must
    combine constraint types instead of following a chain.
    """
    spec = DIFFICULTY_SPEC["logic_order"][difficulty]
    n = spec["n_entities"]
    n_gap, n_immediate, n_negative = spec["n_gap"], spec["n_immediate"], spec["n_negative"]

    for _attempt in range(400):
        names = rng.sample(_NAMES, n)
        order = names[:]  # ground truth, index 0 = earliest
        truth = {nm: i for i, nm in enumerate(order)}

        chosen: list[tuple] = []

        # Adjacency constraints, stated in the true direction.
        imm_pool = [("immediate", order[i], order[i + 1]) for i in range(n - 1)]
        chosen += rng.sample(imm_pool, min(n_immediate, len(imm_pool)))

        # Gap constraints, phrased without saying which of the two came first.
        gap_pool = [
            ("gap", a, b, abs(truth[a] - truth[b]) - 1)
            for a, b in itertools.combinations(names, 2)
            if abs(truth[a] - truth[b]) - 1 >= 1
        ]
        rng.shuffle(gap_pool)
        chosen += gap_pool[:n_gap]

        # Negative position facts.
        neg_pool = [
            ("notpos", nm, p)
            for nm in names for p in range(1, n + 1)
            if truth[nm] != p - 1
        ]
        rng.shuffle(neg_pool)
        chosen += neg_pool[:n_negative]

        # Add precedence constraints until the whole set pins down one order.
        prec_pool = [
            ("before", a, b) if truth[a] < truth[b] else ("before", b, a)
            for a, b in itertools.combinations(names, 2)
        ]
        rng.shuffle(prec_pool)
        for c in prec_pool:
            if _count_solutions(names, chosen) == 1:
                break
            chosen.append(c)

        if _count_solutions(names, chosen) != 1:
            continue

        # Drop anything not carrying its weight, so the surviving set is
        # minimal and no constraint simply hands over the answer.
        pruned = True
        while pruned:
            pruned = False
            for c in list(chosen):
                trial = [x for x in chosen if x is not c]
                if trial and _count_solutions(names, trial) == 1:
                    chosen = trial
                    pruned = True
                    break

        # The defining property: precedence alone must not be enough.
        prec_only = [c for c in chosen if c[0] == "before"]
        if prec_only and _count_solutions(names, prec_only) == 1:
            continue
        if not any(c[0] in ("gap", "immediate", "notpos") for c in chosen):
            continue
        break
    else:  # pragma: no cover - generation invariant
        raise AssertionError(f"could not generate an indirect instance for {task_id}")

    shown = chosen[:]
    rng.shuffle(shown)

    position = rng.randint(1, n)  # 1-indexed
    answer = order[position - 1]

    lines = [_render(c) for c in shown]
    prompt = (
        f"{n} technicians ran a calibration, each finishing at a distinct time.\n"
        + "\n".join(lines)
        + f"\n\nWho finished in position {position} (position 1 = earliest)?"
    )

    # A plausible slip: off-by-one in the position.
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
        params={"n_entities": n, "n_gap": n_gap, "n_immediate": n_immediate,
                "n_negative": n_negative, "n_constraints": len(shown),
                "position": position, "order": order,
                "constraints": [list(c) for c in shown]},
    )


# --------------------------------------------------------------------------
# Family 3: multi-predicate filtering over a small table
# --------------------------------------------------------------------------

def _gen_set_filter(rng: random.Random, difficulty: int, task_id: str) -> Task:
    """Counting rows that satisfy a nested boolean predicate over a table.

    Longer tables plus a predicate tree that is no longer a flat conjunction.
    A numeric column adds threshold comparisons, so a row cannot be dismissed on
    a single categorical lookup. The condition is rendered with explicit
    parentheses, so there is exactly one reading of it.
    """
    spec = DIFFICULTY_SPEC["set_filter"][difficulty]
    n_records, shape, numeric = spec["n_records"], spec["shape"], spec["numeric"]

    def atom(field: str, val: Any, op: str = "eq") -> tuple[str, str, Any]:
        return (field, op, val)

    def ev(r: dict[str, Any], a: tuple[str, str, Any]) -> bool:
        f, op, v = a
        if op == "eq":
            return r[f] == v
        if op == "gt":
            return r[f] > v
        raise ValueError(op)  # pragma: no cover

    def render_atom(a: tuple[str, str, Any]) -> str:
        f, op, v = a
        return f"{f} is greater than {v}" if op == "gt" else f"{f} is {v}"

    for _attempt in range(400):
        items = rng.sample(_ITEMS, min(n_records, len(_ITEMS)))
        while len(items) < n_records:  # table can exceed the distinct-name pool
            items.append(f"{rng.choice(_ITEMS)}-{len(items)}")
        records = [
            {
                "name": nm,
                "color": rng.choice(_COLORS),
                "size": rng.choice(_SIZES),
                "tag": rng.choice(_TAGS),
                "mass": rng.randint(5, 95),
            }
            for nm in items
        ]

        a_color = atom("color", rng.choice(_COLORS))
        a_size = atom("size", rng.choice(_SIZES))
        a_tag = atom("tag", rng.choice(_TAGS))
        a_mass = atom("mass", rng.choice([20, 30, 40, 50, 60, 70]), "gt")

        if shape == "and":
            left, right = rng.sample([a_color, a_size, a_tag], 2)
            parts = [left, a_mass] if numeric else [left, right]
            pred = lambda r: all(ev(r, a) for a in parts)  # noqa: E731
            cond = " and ".join(render_atom(a) for a in parts)
            detail = {"shape": "and", "atoms": [list(a) for a in parts]}

        elif shape == "or_and":
            g1, g2 = rng.sample([a_color, a_size, a_tag], 2)
            pred = lambda r: (ev(r, g1) or ev(r, g2)) and ev(r, a_mass)  # noqa: E731
            cond = (
                f"({render_atom(g1)} or {render_atom(g2)}) "
                f"and {render_atom(a_mass)}"
            )
            detail = {"shape": "or_and", "atoms": [list(g1), list(g2), list(a_mass)]}

        else:  # or_and_not
            g1, g2 = rng.sample([a_color, a_size], 2) if rng.random() < 0.5 else (a_color, a_size)
            pred = lambda r: (  # noqa: E731
                (ev(r, g1) or ev(r, a_mass)) and not (ev(r, g2) and ev(r, a_tag))
            )
            cond = (
                f"({render_atom(g1)} or {render_atom(a_mass)}) "
                f"and not ({render_atom(g2)} and {render_atom(a_tag)})"
            )
            detail = {"shape": "or_and_not",
                      "atoms": [list(g1), list(a_mass), list(g2), list(a_tag)]}

        count = sum(1 for r in records if pred(r))
        # Reject degenerate instances. An answer of 0, 1, or "nearly all" can be
        # reached without doing the filtering work, and a count that equals a
        # single categorical tally would not require the boolean structure.
        if 3 <= count <= n_records - 4:
            break
    else:  # pragma: no cover - generation invariant
        raise AssertionError(f"could not generate non-degenerate instance for {task_id}")

    table = "\n".join(
        f"- {r['name']}: color={r['color']}, size={r['size']}, "
        f"tag={r['tag']}, mass={r['mass']}"
        for r in records
    )
    prompt = (
        f"An inventory lists {n_records} components:\n{table}\n\n"
        f"How many components satisfy the following condition: {cond}?"
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
        params={"n_records": n_records, "numeric": numeric,
                "predicate": detail, "count": count},
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
