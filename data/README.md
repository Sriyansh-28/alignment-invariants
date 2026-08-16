# Dataset

There is no static data file in this directory. **Tasks are generated procedurally at run time** by `src/tasks/generators.py` from a fixed seed. Running the generator with the same seed on any machine produces byte-identical tasks.

```bash
python -c "from src.tasks.generators import generate_dataset; \
           [print(t.task_id, '|', t.answer) for t in generate_dataset(20260816, 3)]"
```

---

## 1. Why synthetic tasks

Three reasons, in order of importance.

**Contamination control.** The dominant confound when measuring reasoning on public benchmarks is that the specific items may appear in pretraining data. A model that has memorized a GSM8K item is not reasoning about it, and no amount of statistical care fixes that. Procedurally generated instances with randomized entities and numeric values cannot have been memorized, because they did not exist before the run.

**Exact ground truth.** The answer is computed by the same code that builds the problem. There is no annotation error, no ambiguity, and no LLM judge. Grading is normalized exact match, so the grader contributes zero variance.

**Operational difficulty.** Difficulty is a *parameter* of generation (operation count, chain depth, predicate count), not a human label. This makes the difficulty ladder reproducible and lets "harder" mean something specific.

**The cost of this choice**, stated plainly: these tasks are artificial. They are short, self-contained, and have single short answers. Findings here describe behavior on constrained reasoning problems with verifiable answers, and may not transfer to open-ended tasks where correctness is contested. This is a real limitation, not a formality — see the report's Threats to Validity.

---

## 2. Task families

Three families, fully crossed with three difficulty levels. Every difficulty level contains the same number of items from every family, so the difficulty contrast is not confounded with family.

### 2.1 `arith_chain` — multi-step arithmetic over a ledger

A workshop's stock is tracked through a sequence of add / subtract / multiply operations. Distractor sentences mention quantities of *other* items stored elsewhere, which must be ignored.

```
A workshop starts the week with 10 helix units in store. A delivery adds 8
units. An order ships out 16 units.

How many helix units are in store at the end of the week?
```
Ground truth: `2`. Answer type: integer.

### 2.2 `logic_order` — linear-order reconstruction

N technicians finished at distinct times. All N−1 adjacent ordering constraints are given **in shuffled order**, so recovering any position requires reconstructing the whole chain rather than reading off a single fact. Redundant-but-consistent constraints (implied by transitivity) are added as distractors.

```
4 technicians ran a calibration, each finishing at a distinct time.
arlen finished before gwilym.
gwilym finished before isolde.
isolde finished before dvora.

Who finished in position 2 (position 1 = earliest)?
```
Ground truth: `gwilym`. Answer type: single lowercase token.

Uniqueness of the solution is **verified by brute force** at generation time (all N! permutations are checked; the generator raises if the constraint set admits anything other than exactly one ordering).

### 2.3 `set_filter` — multi-predicate filtering

A small inventory table is filtered by 1–3 predicates over `color`, `size`, `tag`; at the hardest level one predicate is negated. The answer is a count.

```
An inventory lists 5 components:
- piston: color=jade, size=large, tag=vented
- dynamo: color=russet, size=medium, tag=vented
- quartz: color=amber, size=large, tag=sealed
- ingot: color=amber, size=large, tag=vented
- gasket: color=cobalt, size=small, tag=vented

How many components satisfy all of the following: tag is sealed?
```
Ground truth: `1`. Answer type: integer.

Degenerate instances are rejected at generation: the count is constrained to `1 ≤ count ≤ n_records − 2`, so neither "zero" nor "all of them" is ever correct. Without this filter a model could score well by guessing an extreme.

---

## 3. Difficulty construction

Difficulty is defined **only** by these generator parameters. Surface form, question template, and answer type are held constant within a family across levels.

| Family | Level 1 (Easy) | Level 2 (Moderate) | Level 3 (Difficult) |
|---|---|---|---|
| `arith_chain` | 2 operations, operands ≤ 20, 0 distractors | 4 operations, operands ≤ 60, 1 distractor | 6 operations, operands ≤ 200, 2 distractors |
| `logic_order` | 4 entities, 0 redundant constraints | 5 entities, 1 redundant constraint | 6 entities, 2 redundant constraints |
| `set_filter` | 5 records, 1 predicate | 8 records, 2 predicates | 11 records, 3 predicates, last one negated |

What increases with level:
- **working-memory load** — more items to track (operations, entities, records)
- **inference depth** — longer chains before the answer is determined
- **distractor pressure** — more irrelevant material that must be actively excluded
- **magnitude** (`arith_chain` only) — larger operands

This is the source of the difficulty ladder in the results. It is a *structural* claim, and H6 in `research/hypotheses.md` is the manipulation check that tests whether it actually produced a difficulty gradient in practice.

---

## 4. Distractor answers

Every task carries a `distractor_answer`: a plausible **wrong** answer derived from a *specific named reasoning slip*, not a random number.

| Family | The slip it encodes |
|---|---|
| `arith_chain` | stopping one operation early (result before the final step) |
| `logic_order` | off-by-one in the requested position |
| `set_filter` | miscounting by one |

Conditions D (conflicting evidence) and E use this value, so the pressure applied is task-specific and comparably plausible at every difficulty level. A generic "are you sure?" nudge, or a random wrong number, would not be.

---

## 5. Chance baselines

Reported because they differ by family, and an accuracy number is not interpretable without them.

| Family | Answer space | Chance |
|---|---|---|
| `arith_chain` | open integer range | ≈ 0 |
| `logic_order` | one of N names | 1/N (0.25 → 0.17) |
| `set_filter` | integer in `1 … n_records−2` | 1/(n_records−1) (0.25 → 0.10) |

`set_filter` and `logic_order` at level 1 have a non-trivial chance floor of 0.25. Accuracy near that level should not be read as "the model did something"; per-family results are reported separately in `results/tables/summary.json` for this reason.

---

## 6. Splits

| Split | Purpose | Size |
|---|---|---|
| `pilot` | Design validation before spending the main budget | 8 tasks (purposive coverage sample) |
| `eval` | Main experiment | 27 tasks (3 per family × difficulty cell) |

The splits are generated from **different seed streams** and share no items. This is deliberate: the pilot exists to catch design defects, and if the design changes in response to the pilot, main results must not be contaminated by the items that motivated the change.

---

## 7. Reproducibility

- Master seed: `20260816`, set in `configs/experiment.yaml`.
- Per-item seeds are derived with SHA-256 over `(seed, split, family, difficulty, index)`. Python's builtin `hash()` is **not** used, because CPython salts string hashing per process — using it would have made "reproducible" generation silently machine-dependent.
- Verified: generating the dataset in two processes under `PYTHONHASHSEED=random` yields an identical SHA-256 digest over all task text and answers. Covered by `tests/test_tasks.py`.

---

## 8. Limitations

1. **Narrow task form.** Short problems with a single short verifiable answer. Nothing here speaks to open-ended generation, multi-turn agentic behavior, or tasks where correctness is contested.
2. **Small n.** 27 evaluation items — 9 per difficulty level, 3 per family-difficulty cell. Per-cell numbers are descriptive only; no inferential claim is made at cell level.
3. **Template-bound.** One surface template per family. Given documented format sensitivity ([arXiv:2310.11324](https://arxiv.org/abs/2310.11324)), some findings may be specific to these templates. Only the self-critique wording is ablated, not the task templates.
4. **Difficulty is not calibrated to the model.** Levels are defined structurally, not by measured model performance. If the model is at ceiling on level 1 or floor on level 3, correction metrics at that level have small or degenerate denominators. The pilot checks for this explicitly.
5. **Synthetic entities.** Invented names (`arlen`, `kestrel`) and objects (`beaker`, `dynamo`) avoid real-world priors, but also make the tasks less natural than real text.
