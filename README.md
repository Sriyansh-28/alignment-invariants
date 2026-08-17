# Alignment Invariants

**Alignment Invariants Under Capability and Behavioral Pressure**

An experimental study of whether alignment-relevant behavioral properties of a language model remain stable as task difficulty and behavioral pressure increase.

> **Status: complete.** The pre-registered main experiment ran on 2026-08-16 against `gemini-3.1-flash-lite`: 36 tasks, 6 conditions, 216 trials, 240 live calls, no failures. Every number below is generated from committed experiment output (`results/tables/summary.json`); nothing is estimated or filled in by hand. 140 unit tests pass. The study is closed — no further model calls will be made.
>
> **No pre-registered comparison reached statistical significance.** The primary comparison, neutral reprompt control vs self-critique, gave a Holm-adjusted **p = 0.500**. This study **does not** show that self-critique improves performance or alignment. Full detail in [`research/report.md`](research/report.md).

---

## Research question

> Do alignment-relevant behavioral properties of language models remain stable as task difficulty and behavioral pressure increase?

The project studies four *candidate* properties — behaviors we might want a system to preserve as conditions get harder:

1. **Self-correction** — does the model repair its own errors when asked to review?
2. **Instruction consistency** — does it keep following a stated output contract?
3. **Robustness to misleading information** — does a confident wrong assertion move it off a correct answer?
4. **Confidence/correctness correspondence** — does stated confidence track being right?

**These are not a definition of alignment.** They are measurable proxies chosen because they have objective ground truth. The study asks a narrow question — do they stay stable? — and does not claim that stability implies alignment or that instability implies misalignment.

---

## Motivation

Most alignment questions are about systems that do not yet exist, which makes them hard to study empirically. One tractable reframing: instead of asking whether a model "is aligned," ask **which specific behavioral properties hold up when conditions get harder**, and measure that directly.

A property that holds under easy conditions but collapses under difficulty or pressure is a weak foundation for a safety argument, because deployment conditions are rarely the easy ones. Whether the properties measured here behave that way is an empirical question, and this study is a small, controlled attempt to answer it for one model.

See [`research/background.md`](research/background.md) for the literature review, with every claim tagged **ESTABLISHED** / **HYPOTHESIS** / **SPECULATION**.

---

## Hypotheses

Pre-registered in [`research/hypotheses.md`](research/hypotheses.md) **before** any experimental API call.

**H1 (primary).** Alignment-relevant behavioral properties do not all scale monotonically with difficulty and pressure; different properties degrade or improve at different rates. This is a *dissociation* claim, not a direction claim.

Secondary hypotheses cover: self-critique ineffectiveness (H2), the second-turn confound (H3), sycophancy under conflicting evidence (H4), pressure suppressing correction (H5), the difficulty manipulation check (H6), correction efficacy falling where it is most needed (H7), overconfidence (H8), and format compliance being more stable than accuracy (H9). Explicit null hypotheses are stated for each so that failing to reject one is a reportable outcome.

---

## Related work

The design responds to a specific tension in the literature. Self-Refine reported substantial gains from iterative self-feedback ([arXiv:2303.17651](https://arxiv.org/abs/2303.17651)), while Huang et al. found that intrinsic self-correction without external feedback does not reliably help and can hurt ([arXiv:2310.01798](https://arxiv.org/abs/2310.01798)). Kamoi et al.'s survey concludes the deciding factor is the quality of the feedback signal ([arXiv:2406.01297](https://arxiv.org/abs/2406.01297)), and Stechly et al. found the *content* of critiques largely irrelevant to whether iterative prompting helped ([arXiv:2310.12397](https://arxiv.org/abs/2310.12397)).

Conditions D and E build on documented sycophancy ([arXiv:2310.13548](https://arxiv.org/abs/2310.13548)). Instruction consistency follows IFEval's verifiable-instruction approach ([arXiv:2311.07911](https://arxiv.org/abs/2311.07911)). The confidence analysis is deliberately conservative given that stated confidence is a weaker signal than properly elicited probabilities ([arXiv:2207.05221](https://arxiv.org/abs/2207.05221), [arXiv:2305.14975](https://arxiv.org/abs/2305.14975)).

**The gap addressed:** existing self-correction studies mostly report a single aggregate effect per benchmark, without a controlled difficulty ladder and — critically — **without a turn-matched control**. If baseline is one turn and self-critique is two, the comparison confounds the critique with the extra turn.

---

## Experimental setup

### Model

One model, one configuration. This is a **within-model behavioral study**, not a multi-model benchmark.

- Model: `gemini-3.1-flash-lite` (override via `GEMINI_MODEL`)
- `temperature = 0`, fixed seed, `max_output_tokens = 3072`
- **Thinking tokens disabled** (`thinking_budget = 0`)

The design was written against `gemini-2.5-flash`. That model, and `gemini-2.5-flash-lite`, now return `404 NOT_FOUND` for new API keys, so the study could not run as specified. `gemini-3.1-flash-lite` is the nearest available flash-lite model that still accepts `thinking_budget = 0`; the two nearer-generation flash-lite models reject it, which would have silently reintroduced the confound the setting exists to remove. Recorded as [Addendum 2](research/hypotheses.md#addenda).

That last choice is deliberate and consequential: with hidden reasoning enabled the model may already self-correct internally, which would confound the self-critique condition. Disabling it means all reasoning the intervention can act on is visible in the response text. It also limits the scope of the findings — they describe the non-thinking configuration only.

### Evaluation conditions

Stage 1 is issued **once per task and shared across all six conditions**. This halves cost and, more importantly, makes every comparison exactly paired: all interventions act on the identical initial answer.

| | Condition | Turns | What it isolates |
|---|---|---|---|
| **A** | Baseline | 1 | Initial accuracy; reference point |
| **R** | **Reprompt control** | 2 | A second turn with no evaluative content |
| **B** | Self-critique | 2 | Intrinsic self-correction, no external feedback |
| **C** | Verification | 2 | Independent re-derivation rather than inspection |
| **D** | Conflicting evidence | 2 | A specific plausible wrong answer asserted by a third party |
| **E** | Preserve-answer pressure | 2 | Instruction pressure in tension with accuracy |

**Condition R is the methodological core.** Without it, every B/C/D/E effect is confounded with turn count. The comparison that matters for "does self-critique work" is **R vs B**, not A vs B.

A sixth condition "Increased Task Difficulty" was specified in the original design and **removed before piloting** — difficulty is an orthogonal factor crossed with every condition, not a condition. Recorded in the [hypotheses addendum](research/hypotheses.md#addenda).

### Dataset

Procedurally generated, not drawn from a public benchmark. Full documentation in [`data/README.md`](data/README.md).

- **36 evaluation tasks**, fully crossed: 4 families × 3 difficulty levels × 3 items
- **4 pilot tasks** on a disjoint split (Pilot 3); Pilots 1 and 2 used their own disjoint splits
- Families: `false_premise`, `evidence_update`, `convention`, `instruction_conflict`

Why synthetic: **contamination control** (instances did not exist before the run, so they cannot have been memorized), **exact ground truth** (computed by the generating code — no LLM judge anywhere), and **operational difficulty** (a generator parameter, not a human label).

Each family targets a situation where a competent reader can go wrong in a specific, predictable, checkable way:

| Family | Behaviour measured | The natural error |
|---|---|---|
| `false_premise` | checking a question's presupposition against the evidence | answering a question the log contradicts |
| `evidence_update` | applying a stated precedence rule over a positional heuristic | trusting the first- or last-listed record |
| `convention` | letting an explicit local convention override a strong prior | reading dates as month/day |
| `instruction_conflict` | keeping a stated priority ordering under a competing inline request | obeying the nearer instruction |

Difficulty is structural, with the surface template held constant within a family across levels:

| Family | L1 | L2 | L3 |
|---|---|---|---|
| `false_premise` | 3 records | 5 records | 7 records, entities referred to by attribute |
| `evidence_update` | 2 revisions | 3 revisions, 2 fields | 4 revisions, newest withdrawn |
| `convention` | 2 dates | 3 dates | 4 dates, second-earliest asked |
| `instruction_conflict` | 1 inline request | 2 inline requests | 2 requests + tagged policy exception |

Two families are **discriminative by construction**: a `convention` item is rejected unless its answer differs under the two date readings, and `false_premise` items are balanced so answering `NONE` always scores no better than answering a number always.

**These are Revision 3 families.** The original three (`arith_chain`, `logic_order`, `set_filter`) were retired after two pilots scored 48/48 at stage 1 — see [What did not work](#what-did-not-work).

Every task carries a `distractor_answer` derived from a *named reasoning slip* — the answer reached by taking the tempting route — so conditions D and E apply task-specific pressure of comparable plausibility at every difficulty level.

### Metrics

Defined operationally in [`research/metrics.md`](research/metrics.md), implemented in `src/metrics/metrics.py`, unit-tested.

Initial Accuracy · Final Accuracy · Error Detection Rate · False Detection Rate · Successful Correction Rate · False Correction Rate · Error Persistence Rate · Answer Change Rate · Instruction Consistency · Response Consistency · Confidence/Calibration (gated)

Two rules enforced in code:

1. **A rate with a zero denominator is `undefined`, never `0.0`.** A model that made no errors has no correction rate.
2. **Every rate carries its numerator and denominator.** "100% (2/2)" and "100% (40/40)" are different claims.

Successful Correction Rate is **never reported without False Correction Rate**. An intervention that fixes three errors while breaking four is a net harm, and reporting only the correction rate would hide that.

---

## Results

36 tasks, 216 paired trials, `gemini-3.1-flash-lite`. From `results/tables/summary.json`.

**Baseline accuracy 31/36 = 0.861** (Wilson 0.713–0.939). **Five first-pass errors** — the denominator for every correction measure here.

| Condition | Final accuracy | Corrected | False-corrected |
|---|---|---|---|
| A. Baseline | 31/36 = 0.861 | — | — |
| **R. Reprompt control** | **34/36 = 0.944** | **3/5** | 0/31 |
| **B. Self-critique** | **36/36 = 1.000** | **5/5** | 0/31 |
| C. Verification | 34/36 = 0.944 | 3/5 | 0/31 |
| D. Conflicting evidence | 35/36 = 0.972 | 4/5 | 0/31 |
| E. Preserve pressure | 35/36 = 0.972 | 4/5 | 0/31 |

**No intervention broke a correct answer** — false correction 0/31 everywhere, including both pressure conditions. Format compliance 36/36 in every condition.

**Baseline by difficulty:** d1 12/12 · d2 11/12 · d3 8/12 — monotone, but 12 items per level is a weak check.

**Baseline by family:** `false_premise` 9/9 · `convention` 9/9 · `evidence_update` 8/9 · **`instruction_conflict` 5/9**. Four of the five errors come from one family; the study is effectively one discriminating family plus three that did not discriminate on this model.

**Confidence: unavailable.** Stated confidence was 100 on 215 of 216 trials (one verification trial gave 95). No condition reached the pre-registered minimum of three distinct values, so ECE was not computed. Reported as unmeasurable rather than approximated.

**Consistency probe: 12/12** identical on repeat at temperature 0 — API determinism, but it does rule out sampling noise as an explanation for the differences above.

**Prompt ablation: uninformative.** All 12 ablation items were already correct at stage 1, so there was nothing to correct and no discordant pairs.

### What this does and does not show

The neutral reprompt control — which adds a turn and **no evaluative content at all** — recovered 3 of the same 5 errors that self-critique recovered 5 of, and the two are not statistically distinguishable. Whatever fixed those three cannot have been critique, because none was requested.

Had this study compared baseline against self-critique alone, it would have reported 0.861 → 1.000 and credited the critique. The turn-matched control is what stops that inference. **A substantial part of the apparent self-critique benefit is explained by simply being asked again**, consistent with [arXiv:2310.12397](https://arxiv.org/abs/2310.12397).

**This study does not establish that self-critique improves performance or alignment.**

## Statistical analysis

Because the same tasks are evaluated under every condition, the analysis is **paired throughout**:

- **Exact McNemar** for condition-vs-condition accuracy. A two-sample proportion test would ignore the pairing and overstate variance; the exact binomial version is used because discordant counts here are small, where the chi-square approximation is anticonservative.
- **Wilson score intervals** for proportions — at n ≈ 27 with rates near 0 or 1, Wald intervals undercover and can leave [0,1].
- **Percentile bootstrap, clustered on task**, for correction rates, whose denominators are themselves random.
- **Cochran's Q** as an omnibus test before any pairwise comparison.
- **Cochran–Armitage** for the difficulty ladder, because difficulty is *ordered* and a plain chi-square would discard that.
- **Holm–Bonferroni** across the pre-registered family of 5 comparisons (controls family-wise error; uniformly more powerful than Bonferroni).

**Power is reported alongside every null result.** With 36 paired items the minimum detectable risk difference at 80% power is **≈0.256**. **Every non-significant result below means "underpowered to detect," not "no effect."**

### Results

Cochran's Q omnibus: **Q = 12.71, df = 5, p = 0.026**.

| Comparison | acc A | acc B | discordant | p raw | **p Holm** | Reject |
|---|---|---|---|---|---|---|
| **R. Reprompt vs B. Self-critique** (primary) | 0.944 | 1.000 | 0 / 2 | 0.500 | **0.500** | **No** |
| A. Baseline vs B. Self-critique | 0.861 | 1.000 | 0 / 5 | 0.063 | 0.313 | No |
| A. Baseline vs R. Reprompt | 0.861 | 0.944 | 0 / 3 | 0.250 | 0.500 | No |
| A. Baseline vs D. Conflicting evidence | 0.861 | 0.972 | 0 / 4 | 0.125 | 0.500 | No |
| A. Baseline vs E. Preserve pressure | 0.861 | 0.972 | 0 / 4 | 0.125 | 0.500 | No |

**No pre-registered comparison is significant after correction.** Every observed difference is smaller than the 0.256 detectable threshold.

The omnibus is nominally significant while no corrected pairwise test is — an ordinary consequence of pooling evidence across six conditions when each pairwise test sees only 2–5 discordant pairs. **It licenses no specific claim about which conditions differ**, and no uncorrected or post-hoc pairwise analysis was run to manufacture one.

The primary comparison rests on **two discordant pairs**. Exact McNemar cannot return p < 0.05 below five, so this test could not have been significant under this design — a foreseeable limitation given the pilot's five baseline errors.

## Failure cases

All 216 trials classified by deterministic rule; counts sum to the total.

| Category | Count |
|---|---|
| `stable_correct` | 171 |
| `successful_correction` | 19 |
| `false_detection_survived` | 15 |
| `silent_persistence_of_error` | 7 |
| `confident_persistence_of_error` | 4 |
| `unparseable_response` | 0 |
| `false_correction` | 0 |

**`false_detection_survived` (15)** is the notable one: the model called a *correct* answer incorrect and then kept it anyway. Stated assessment and behaviour came apart, and behaviour was the reliable channel. A study reading only final accuracy would never see it.

`analysis/failure_analysis.py` classifies **every** trial into one of nine mutually exclusive categories by a deterministic rule — `confident_persistence_of_error`, `detected_but_uncorrected`, `false_correction`, and so on. Counts sum to the total, and qualitative examples are selected by a fixed rule (first N by sorted task id), **not** by which ones look interesting.

## What did not work

Recorded so far, before any model run:

- **Condition "F. Increased Task Difficulty" was removed.** It is not a condition — difficulty is an orthogonal factor crossed with every condition. Keeping it would have made the central question ("does the self-critique effect change with difficulty?") unanswerable.
- **Reproducibility bug caught in development.** Per-item seeds initially used Python's builtin `hash()`, which CPython salts per process. Dataset generation would have been silently machine-dependent. Now SHA-256 based, with a test that runs generation under three `PYTHONHASHSEED` values and asserts identical output.
- **Cache-poisoning bug caught in development.** The mock provider originally wrote cache entries under keys identical to real calls, so a mock run followed by a real run would have silently served synthetic data as model output. The cache is now namespaced by provider, with a regression test.
- **Parser bug caught by tests.** The confidence regex did not tolerate markdown *after* the colon (`**CONFIDENCE:** 75`), which would have silently dropped confidence data.

### From the run itself

- **Two pilots produced no usable data.** Pilots 1 and 2 both scored 48/48 at stage 1 — 96 live calls, about a quarter of the budget, yielding no measurable behaviour. Pilot 2 raised reasoning depth substantially (output tokens 9.6k → 25k for the same 48 calls, with visible backtracking in transcripts) and *still* produced zero first-pass errors. That is what motivated changing the task type rather than scaling further. `logic_order` turned out structurally incapable of being made hard: a set of pure precedence constraints has a unique linear extension only when it contains every adjacent pair, which is a chain walk.
- **The gate blocked the main run twice**, and did its job. The cost was real; the alternative was spending the full budget on a saturated instrument.
- **A ground-truth bug found by rewriting the tests.** Making the tests re-derive answers by parsing the *rendered prompt* rather than trusting generator bookkeeping immediately exposed negative-position constraints comparing a 0-indexed position against the 1-indexed one shown to the model. Every ordering instance was unsolvable as written while looking well-formed.
- **A dormant cache bug that would have replayed failures as data.** Failed calls were cached and served back as ordinary hits, so a rerun after a bad session would have silently presented failures as model output. Fixed before the main run, with regression tests.
- **The confidence instruction could not be made to work.** Three attempts across three pilots, including an instruction defining the scale operationally, all returned 100 on essentially every trial. Calibration is reported as unavailable.
- **The prompt ablation carried no information.** All 12 ablation items were already correct at stage 1.
- **A budget accounting overrun.** 389 API requests against an approved 370. See [`research/report.md` §11](research/report.md#11-experimental-accounting-incident).

---

## Limitations

1. **n = 36, and only 5 baseline errors.** Every correction measure rests on those five. The minimum detectable difference is ≈0.26; every observed difference is smaller. Per-cell numbers are descriptive only.
2. **The error signal comes from one family.** Four of five baseline errors were `instruction_conflict`; the other three families were at or near ceiling on this model.
3. **One model, one configuration** — and not the model the design was written against, since the original was withdrawn from new keys mid-study. Thinking tokens disabled.
4. **Synthetic, narrow tasks.** Short problems with single verifiable answers. Nothing here speaks to open-ended generation or tasks where correctness is contested.
5. **One prompt phrasing per condition.** Given documented format sensitivity ([arXiv:2310.11324](https://arxiv.org/abs/2310.11324)), effects may be phrasing-specific. Only the self-critique wording is ablated.
6. **Calibration is unavailable, not weak.** Stated confidence took one value on 215 of 216 trials; ECE was gated off, as pre-registered.
7. **Response consistency at temperature 0** measures API determinism, not sampling variability.

## Threats to validity

- **Capability/alignment confound.** A drop at difficulty 3 may simply mean the task got harder. This study cannot separate the two, and does not claim to.
- **Ceiling effects, which actually bit.** Two full pilots sat at 48/48 before the instrument was replaced. Even in the main run, three of four families and difficulty level 1 were at ceiling, so the realized error denominator was five.
- **Chance baselines differ by family** (0.5 for `instruction_conflict`'s two salient candidates, lower elsewhere), so aggregate accuracy mixes families with different guess floors. Per-family results are reported separately.
- **Condition R controls for turn count but not for evaluative framing** — it does not request a self-assessment. This became the study's central interpretive limit: R and B differed on only two items, so the design could not separate the critique from the extra turn. A stricter control is future work.
- **Difficulty is defined structurally, not calibrated to the model.** The levels may not be equally spaced in model-difficulty.

---

## Reproducibility

```bash
git clone https://github.com/Sriyansh-28/alignment-invariants
cd alignment-invariants
pip install -r requirements.txt

cp .env.example .env        # then add your key from https://aistudio.google.com/apikey

# See the exact call plan without spending anything
python -m src.run_experiment --config configs/experiment.yaml --phase pilot --dry-run

# Pilot (48 calls)
python -m src.run_experiment --config configs/experiment.yaml --phase pilot

# Validate the pilot BEFORE spending the rest of the budget.
# Exits non-zero if any gate fails, so it can guard the main run.
python -m analysis.pilot_gate --results experiments/pilot_results.json

# Main experiment (≤186 calls) — only after the gate passes
python -m src.run_experiment --config configs/experiment.yaml --phase main

# Analysis: tables, figures, failure categorization
python -m analysis.analyze_results --results experiments/main_results.json
python -m analysis.failure_analysis --results experiments/main_results.json

# Tests (no network access required)
python -m pytest tests/ -q

# Exercise the whole pipeline with zero API calls
python -m src.run_experiment --phase main --mock
```

- **Seeds.** Master seed in `configs/experiment.yaml`. Per-item seeds are SHA-256 derived, verified stable across processes and `PYTHONHASHSEED` values.
- **Configuration.** No experiment parameter requires a source edit. Prompts live in `configs/prompts.yaml`; the design lives in `configs/experiment.yaml`.
- **Cache is committed.** `cache/` is the raw experimental record, so anyone can reproduce every number **without a key and without spending quota**: `--offline` serves entirely from cache and aborts on a miss.
- **Mock provider.** `--mock` runs the full pipeline deterministically. Its output is namespaced separately in the cache, written to a `_MOCK` filename, and flagged `is_real_model_output: false`, so mock output cannot be mistaken for model output.

### Repository layout

```
configs/     experiment.yaml, prompts.yaml   — all parameters and prompt text
src/         tasks/ gemini/ evaluation/ metrics/ caching/ run_experiment.py
analysis/    statistical_tests.py, analyze_results.py, failure_analysis.py
data/        README.md (dataset is generated, not stored)
research/    background.md, hypotheses.md, metrics.md, report.md
experiments/ raw run output (JSON)
results/     tables/ and figures/ — generated, never hand-edited
tests/       140 unit tests
web/         Next.js dashboard and live demonstration
```

---

## Live demo

A Next.js + TypeScript + Tailwind app in [`web/`](web/).

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

The **dashboard** renders only from committed experiment output (`results/tables/summary.json`, copied into `public/data/` by `npm run sync`). If no results exist it shows "Experiments pending" rather than placeholder numbers. Mock results trigger a prominent warning banner.

The **live demonstration** runs two real model calls on one predefined task and shows the initial answer, the revised answer, the ground truth, and which failure category the outcome falls into. It is explicitly labelled *Research demonstration — not a production safety evaluation*, and a single trial is not evidence.

Security properties of the demo endpoint:

- The key is read **only** inside a server route handler (`app/api/demo/route.ts`). Verified absent from the client bundle; no `NEXT_PUBLIC_` variable is used anywhere.
- **The client cannot supply prompt text.** It selects a task id and a condition name from fixed server-side allow-lists. Otherwise the endpoint would be an open relay to the operator's quota.
- Rate limited per IP (6 per 10 min) and per process (`DEMO_GLOBAL_CALL_LIMIT`, default 200), with an in-process response cache.
- Provider exception text is never echoed to the browser.

### Deploying to Vercel

1. Push to GitHub.
2. Import the repo at [vercel.com/new](https://vercel.com/new) and set **Root Directory** to `web`.
3. Add environment variables (**Environment Variables**, not build args): `GEMINI_API_KEY`, optionally `GEMINI_MODEL` and `DEMO_GLOBAL_CALL_LIMIT`.
4. Deploy. Do **not** prefix the key with `NEXT_PUBLIC_` — that would inline it into the browser bundle.

If `GEMINI_API_KEY` is unset, the demo returns a clear 503 and the dashboard still works, since it reads committed results.

---

## Free API requirement

This project runs entirely on the **Google Gemini API free tier**. No paid model API is used.

**The free tier is subject to Google's current limits, which change without notice.** At the time of writing Google no longer publishes a static free-tier table and directs users to [their AI Studio rate-limit page](https://aistudio.google.com/rate-limit); reported free-tier request-per-day quotas for Flash models have been reduced substantially. Check your own limits before running, and set `GEMINI_MODEL` to a model your account can access on the free tier.

Cost control is enforced in code, not by convention:

- **A persistent cumulative ledger** (`experiments/budget_ledger.json`) debits every live request across all runs and sessions — diagnostic, pilot and main alike, successes and failures. `BudgetGuard` alone was not enough: it counts within one process, and the first two pilots each reported "202 remaining" while together spending 96 calls.
- **The full call schedule is computed before any request is issued**, cache-aware, so a resume reserves only what it will actually cost. A plan that would breach the cap aborts having spent nothing. Check it with `--dry-run`.
- **Every response is cached** and keyed on the complete request. Re-running the main phase costs **zero** calls.
- **Only successful responses are cached.** Failures are never persisted and are always retried — an earlier revision cached them and replayed them as model output.
- **Stage 1 is shared across all six conditions**, halving cost versus re-asking per condition.
- Failed calls count against the budget, because they consume quota. Retries count individually, because the quota is charged per request.
- Rate limits are retried with exponential backoff; if the provider still refuses, the run **stops cleanly and resumes from cache** after the quota window resets rather than burning the next window.

**Realized spend: 389 requests** (the main run's 240 logical calls issued 259 HTTP requests, 19 of them retries). The cap was raised once, 250 → 370, as an audited ledger entry, to fund the pre-registered main design without shrinking it. The run then overran that cap by 19 requests — fully documented in [`research/report.md` §11](research/report.md#11-experimental-accounting-incident). The overrun is left visible in the ledger rather than reconciled away.

Inspect the ledger at any time:

```bash
python -m src.caching.ledger
```

### The pilot gate

The main run is gated on the pilot. `analysis/pilot_gate.py` mechanically checks five conditions before the remaining budget is spent, and exits non-zero if any fail:

1. **Ground truth is valid** — answers non-empty and normalized, distractors distinct from truth, integer answers parse as integers.
2. **Metrics are computable** — initial accuracy defined, and the baseline actually produced errors (otherwise every correction rate has an empty denominator).
3. **Conditions are meaningfully different** — at least one intervention moves at least one answer; inert manipulations are flagged.
4. **No obvious confound** — accuracy is off both ceiling and floor, and the difficulty profile is inspected (a non-monotone ladder is surfaced loudly, since it would make every difficulty claim uninterpretable).
5. **Response format is stable** — format compliance and parse rate above threshold, zero failed calls, and the distinct-confidence-value count checked against the pre-registered ECE gate.

A failed gate means fixing the design and re-piloting, with the change recorded in `research/hypotheses.md` — not adjusting thresholds until it passes.

---

## Future research

- Repeat at temperature > 0 to measure genuine sampling-induced consistency rather than API determinism.
- Repeat with thinking tokens enabled, to test whether visible-reasoning self-correction differs from hidden-reasoning self-correction.
- Widen the prompt ablation across all conditions, reporting performance ranges over phrasings rather than point estimates.
- Increase n substantially; the present study is underpowered by design given the free-tier budget.
- Add a stricter control that includes an evaluative frame but no critique request, separating "asked to evaluate" from "asked to critique."
- Test whether the *content* of a critique matters by injecting deliberately wrong critiques, following [arXiv:2310.12397](https://arxiv.org/abs/2310.12397).

---

## Citation

```bibtex
@misc{alignment_invariants_2026,
  title  = {Alignment Invariants Under Capability and Behavioral Pressure},
  author = {Sriyansh},
  year   = {2026},
  note   = {Experimental study of behavioral stability in language models},
  url    = {https://github.com/Sriyansh-28/alignment-invariants}
}
```

## License

MIT — see [LICENSE](LICENSE).
