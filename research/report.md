# Alignment Invariants Under Capability and Behavioral Pressure

**Status: complete.** The pre-registered main experiment ran on 2026-08-16 against `gemini-3.1-flash-lite`. **No number in this document is estimated, projected, or written by hand** — every figure below is read from `results/tables/summary.json`, itself generated from `experiments/main_results.json`. The study is closed: no further model calls will be made, and no analysis beyond the pre-registered plan has been run.

**Headline: no pre-registered comparison reached statistical significance.** The instrument worked, the interventions moved answers, and the study was too small to distinguish the candidate explanations. That is the result.

---

## Abstract

`gemini-3.1-flash-lite` was evaluated on 36 procedurally generated tasks across four families and three structurally-defined difficulty levels, under six conditions: baseline, a neutral reprompt control, self-critique, verification, conflicting evidence, and preserve-answer pressure. All interventions act on the same stage-1 answer, so comparisons are exactly paired. 216 trials, 240 live API calls, no failures, no unparseable responses.

Baseline accuracy was **31/36 (0.861)**. Five items were answered incorrectly on the first pass, and those five errors are the entire denominator for every correction measure in this study. Final accuracy was **36/36** under self-critique, **34/36** under the neutral reprompt control, 34/36 under verification, and 35/36 under both pressure conditions. No condition broke a correct answer: the false-correction rate was **0/31 everywhere**.

A Cochran's Q omnibus across the six conditions returned p = 0.026, but **none of the five pre-registered pairwise comparisons survived Holm correction**. The primary comparison — neutral reprompt control versus self-critique — was 0.944 vs 1.000, exact McNemar p = 0.500, **Holm-adjusted p = 0.500**. With 36 paired items the minimum detectable difference is ≈0.26, so these nulls mean *underpowered*, not *no effect*.

The neutral reprompt control corrected **3 of the same 5 errors** that self-critique corrected 5 of. Since that control adds a turn and no evaluative content, a substantial part of the apparent self-critique benefit is consistent with simply being asked again. This study cannot separate the two.

Stated confidence was 100 on 215 of 216 trials, so **calibration is unavailable**, not merely weak. The consistency probe agreed 12/12 at temperature 0, confirming the comparisons are not sampling noise.

**This study does not establish that self-critique improves performance or alignment.**

---

## 1. Introduction

Alignment questions are usually posed about systems that do not yet exist, which makes them difficult to study empirically. A tractable reframing is to stop asking whether a model "is aligned" and instead ask a narrower question with a measurable answer: **which behavioral properties stay put when conditions get harder?**

This study calls such candidate properties *alignment invariants*. The term is descriptive. It is not a claim that the properties measured are necessary or sufficient for alignment — they are proxies chosen because they admit objective ground truth.

The contribution is methodological as much as empirical. Most published self-correction results compare one-turn generation against a two-turn critique pipeline, which confounds the critique with the additional turn. This study adds a turn-matched control and a structurally-defined difficulty ladder, and reports the cost of intervening (correct answers broken) alongside the benefit (errors fixed).

---

## 2. Research question

> Do alignment-relevant behavioral properties of language models remain stable as task difficulty and behavioral pressure increase?

Four candidate properties, chosen for measurability:

1. Self-correction
2. Instruction consistency
3. Robustness to misleading/conflicting information
4. Confidence/correctness correspondence, where measurable

---

## 3. Related work

Summarized here; full treatment with claim tagging in [`background.md`](background.md).

The literature contains a live disagreement. Self-Refine reported large gains from iterative self-feedback ([arXiv:2303.17651](https://arxiv.org/abs/2303.17651)). Huang et al. found intrinsic self-correction unreliable and sometimes harmful ([arXiv:2310.01798](https://arxiv.org/abs/2310.01798)). Kamoi et al. reconcile these by identifying feedback quality as the deciding variable ([arXiv:2406.01297](https://arxiv.org/abs/2406.01297)), and Stechly et al. found critique *content* largely irrelevant to whether iterative prompting helped ([arXiv:2310.12397](https://arxiv.org/abs/2310.12397)).

Conditions D and E rest on documented sycophancy ([arXiv:2310.13548](https://arxiv.org/abs/2310.13548)). Instruction consistency follows IFEval's verifiable-instruction approach ([arXiv:2311.07911](https://arxiv.org/abs/2311.07911)). The confidence analysis is deliberately conservative: stated confidence is a much weaker signal than probabilities elicited under a proper scoring rule ([arXiv:2207.05221](https://arxiv.org/abs/2207.05221), [arXiv:2305.14975](https://arxiv.org/abs/2305.14975)). Model self-reports are treated as behavioral outputs, not as evidence about internal states ([arXiv:2305.04388](https://arxiv.org/abs/2305.04388)).

---

## 4. Hypotheses

Pre-registered in [`hypotheses.md`](hypotheses.md) before any experimental call, with explicit null hypotheses and a fixed analysis plan.

**H1 (primary).** Behavioral properties do not all scale monotonically with difficulty and pressure; different properties degrade at different rates. A *dissociation* claim.

**H2–H9 (secondary).** Self-critique ineffectiveness; the second-turn confound; conflicting evidence harming more than self-critique; pressure suppressing correction; the difficulty manipulation check; correction efficacy falling where most needed; overconfidence; format compliance more stable than accuracy.

---

## 5. Method

### 5.1 Design

Within-model, fully paired. **36 tasks × 6 conditions = 216 trials**, with difficulty (3 levels) and task family (4) crossed, 3 items per family-difficulty cell.

**Stage 1 is issued once per task and shared across all six conditions.** This is both a cost measure (halving calls) and a methodological one: every intervention acts on the *identical* initial answer, so condition differences cannot arise from having sampled a different starting point.

| | Condition | Turns | Isolates |
|---|---|---|---|
| A | Baseline | 1 | Initial accuracy |
| R | Reprompt control | 2 | A second turn with no evaluative content |
| B | Self-critique | 2 | Intrinsic self-correction |
| C | Verification | 2 | Independent re-derivation |
| D | Conflicting evidence | 2 | A plausible wrong answer from a third party |
| E | Preserve-answer pressure | 2 | Instruction pressure against accuracy |

**Condition R is the design's core.** The comparison that answers "does self-critique work" is **R vs B**, not A vs B. Without R, the A→B difference conflates the critique with the extra turn.

### 5.2 Model configuration

One model, `gemini-3.1-flash-lite`, `temperature = 0`, fixed seed, `max_output_tokens = 3072`, **thinking tokens disabled**.

Disabling hidden reasoning is deliberate: with it enabled the model may self-correct internally, confounding condition B. The cost is that findings describe the non-thinking configuration only.

The model is not the one the design was written against. `gemini-2.5-flash` and `gemini-2.5-flash-lite` both return `404 NOT_FOUND` for new API keys, so the study could not run as originally specified. `gemini-3.1-flash-lite` was selected as the nearest available flash-lite model that still accepts `thinking_budget = 0` — the two nearer-generation flash-lite models reject it, which would have silently reintroduced the confound condition B exists to avoid. Recorded as [Addendum 2](hypotheses.md#addenda). Absolute accuracies here are not comparable to any result on `gemini-2.5-flash`.

`max_output_tokens` was raised from 1024 to 3072 after Pilot 2 truncated two responses mid-reasoning ([Addendum 4](hypotheses.md#addenda)). With thinking disabled, all reasoning is visible output and needs room.

### 5.3 Task construction

Procedurally generated (see [`../data/README.md`](../data/README.md)), for contamination control, exact ground truth computed by the generating code, and difficulty as a generator parameter rather than a human label.

**Four families**, adopted after two pilots at ceiling ([Addendum 4](hypotheses.md#addenda)):

| Family | Behaviour measured | Natural error |
|---|---|---|
| `false_premise` | checking a question's presupposition against the evidence | answering a question the log contradicts |
| `evidence_update` | applying a stated precedence rule over a positional heuristic | trusting the first- or last-listed record |
| `convention` | letting an explicit local convention override a strong prior | reading dates as month/day |
| `instruction_conflict` | keeping a stated priority ordering under a competing inline request | obeying the nearer instruction |

The original families (`arith_chain`, `logic_order`, `set_filter`) were retired. Two pilots scored 48/48 at stage 1; the second raised reasoning depth substantially (output tokens 9.6k → 25k for the same 48 calls, with visible backtracking) and still produced zero first-pass errors. Deterministic, fully specified procedural puzzles are the class where patient step-by-step execution always succeeds, so scaling them buys latency and truncation rather than measurable error. `logic_order` was structurally incapable of being made hard: a set of pure precedence constraints has a unique linear extension only when it contains every adjacent pair, which is a chain walk.

Ground truth is never produced by an LLM judge, so the grader contributes zero variance. Grading is normalized exact match. Two families are discriminative *by construction*: a `convention` item is rejected unless its answer differs under the two date readings, and `false_premise` items are balanced so that answering `NONE` always scores no better than answering a number always.

Each task carries a `distractor_answer` derived from a *named reasoning slip* — the answer reached by taking the tempting route — so conditions D and E apply comparably plausible pressure at every level.

### 5.4 Metrics

Defined in [`metrics.md`](metrics.md). Two rules enforced in code: a rate with a zero denominator is **undefined**, never 0.0; and every rate carries its numerator and denominator. Successful Correction Rate is never reported without False Correction Rate.

### 5.5 Statistical procedures

Paired throughout, because the same tasks appear under every condition.

- **Exact McNemar** for paired accuracy comparisons — an unpaired proportion test would ignore the pairing and overstate variance; the exact version is used because discordant counts are small.
- **Wilson intervals** for proportions — Wald intervals undercover at this n and can leave [0,1].
- **Percentile bootstrap clustered on task** for correction rates with random denominators.
- **Cochran's Q** omnibus before pairwise tests.
- **Cochran–Armitage** for the ordered difficulty ladder.
- **Holm–Bonferroni** over the pre-registered family of 5 comparisons.

Minimum detectable effect is reported with every null result.

### 5.6 Budget and reproducibility

A persistent cumulative ledger (`experiments/budget_ledger.json`) debits every live request across all runs and sessions — diagnostic, pilot and main alike, successes and failures. Runs abort before spending if they would breach the cap. The cap was raised once, from 250 to 370, as an audited entry with a stated reason, to fund the pre-registered main design without reducing it.

Realized spend was **389 requests against a 370 cap** — an overrun of 19, documented in [§11](#11-experimental-accounting-incident).

Every successful response is cached and the cache is committed, so all results are reproducible without an API key. A re-run of the main phase needs **0 live calls**.

---

## 6. Experimental setup

| | |
|---|---|
| Model | `gemini-3.1-flash-lite` |
| Run window (UTC) | 2026-08-16 20:10:16 → 20:29:34 |
| Tasks / conditions / trials | 36 / 6 / 216 |
| Live calls | 240 (36 stage-1, 180 stage-2, 12 consistency, 12 ablation) |
| Successful / failed | 240 / 0 |
| Cache hits during the run | 24 |
| Tokens (prompt / output) | 78,021 / 29,878 |
| Unparseable responses | 0 |

Realized API **requests** were 259, not 240; see [§11](#11-experimental-accounting-incident).

---

## 7. Results

All figures from `results/tables/summary.json`.

### 7.1 Baseline

**Initial accuracy 31/36 = 0.861** (Wilson 95% CI 0.713–0.939). **Five first-pass errors.** Those five are the denominator for every correction rate in this study, and no amount of downstream analysis can enlarge them.

### 7.2 By condition

| Condition | Final accuracy | Corrected | False-corrected | Answers changed |
|---|---|---|---|---|
| A. Baseline | 31/36 = 0.861 | — | — | 0/36 |
| R. Reprompt control | 34/36 = 0.944 | **3/5** | 0/31 | 3/36 |
| B. Self-critique | **36/36 = 1.000** | **5/5** | 0/31 | 5/36 |
| C. Verification | 34/36 = 0.944 | 3/5 | 0/31 | 3/36 |
| D. Conflicting evidence | 35/36 = 0.972 | 4/5 | 0/31 | 4/36 |
| E. Preserve pressure | 35/36 = 0.972 | 4/5 | 0/31 | 4/36 |

**The false-correction rate was 0/31 in every condition.** No intervention broke a correct answer, including the two pressure conditions. Instruction consistency (format compliance) was 36/36 everywhere.

Correction counts of 3, 4 and 5 are all drawn from the same five items. They are five paired observations, not 25.

### 7.3 By difficulty (baseline)

| | d1 | d2 | d3 |
|---|---|---|---|
| Initial accuracy | 12/12 = 1.000 | 11/12 = 0.917 | 8/12 = 0.667 |

Monotone decreasing, so the difficulty manipulation did something. With 12 items per level this is a weak check, not a validated ladder.

### 7.4 By family (baseline)

| Family | Initial accuracy |
|---|---|
| `false_premise` | 9/9 = 1.000 |
| `convention` | 9/9 = 1.000 |
| `evidence_update` | 8/9 = 0.889 |
| `instruction_conflict` | **5/9 = 0.556** |

**Four of the five baseline errors came from one family.** `instruction_conflict` carries this study's error signal almost single-handedly; the other three families were at or near ceiling. The instrument is really one discriminating family plus three that mostly did not discriminate on this model.

### 7.5 Confidence

Stated confidence was **100 on 215 of 216 trials**; a single verification trial reported 95. No condition reached the pre-registered minimum of three distinct values.

**Calibration is unavailable.** ECE was not computed, and the mean-confidence-minus-accuracy gaps in `summary.json` should not be read as calibration measurements. This was the third attempt across three pilots to elicit a usable confidence distribution, including an instruction that defined the scale operationally. It appears to be a property of the model under this configuration.

### 7.6 Probes

**Response consistency 12/12**, zero disagreements, at temperature 0 with a fixed seed. This measures API determinism rather than behavioural variability — but it does establish that the condition differences above are not sampling noise.

**Prompt ablation** (`self_critique_alt`, terser wording, 12 tasks): 12/12 initial, 12/12 final, 0 answers changed. All 12 items were already correct at stage 1, so the ablation had nothing to correct and **carries no information** about wording sensitivity. There were no discordant pairs; the comparison against condition B is vacuous.

---

## 8. Statistical analysis

### 8.1 Omnibus

Cochran's Q across the six paired conditions: **Q = 12.71, df = 5, p = 0.026**.

### 8.2 Pre-registered pairwise comparisons

Exact McNemar on discordant pairs, Holm-corrected over the pre-registered family of five.

| Comparison | acc A | acc B | discordant | risk diff [95% CI] | p raw | **p Holm** | Reject |
|---|---|---|---|---|---|---|---|
| **R. Reprompt vs B. Self-critique** (primary) | 0.944 | 1.000 | 0 / 2 | 0.056 [0.000, 0.139] | 0.500 | **0.500** | **No** |
| A. Baseline vs B. Self-critique | 0.861 | 1.000 | 0 / 5 | 0.139 [0.028, 0.250] | 0.063 | 0.313 | No |
| A. Baseline vs R. Reprompt | 0.861 | 0.944 | 0 / 3 | 0.083 [0.000, 0.194] | 0.250 | 0.500 | No |
| A. Baseline vs D. Conflicting evidence | 0.861 | 0.972 | 0 / 4 | 0.111 [0.028, 0.222] | 0.125 | 0.500 | No |
| A. Baseline vs E. Preserve pressure | 0.861 | 0.972 | 0 / 4 | 0.111 [0.028, 0.222] | 0.125 | 0.500 | No |

**No pre-registered comparison is significant at α = 0.05 after correction.**

### 8.3 The omnibus/pairwise split

The omnibus is nominally significant while every corrected pairwise test is not. This is an ordinary consequence of a small, highly consistent design: the omnibus pools evidence across all six conditions, while each pairwise test sees only its own discordant pairs — 2 for the primary comparison, 5 at most.

**The correct reading is that the omnibus does not license any specific claim about which conditions differ.** Reporting an uncorrected pairwise p-value, or picking the comparison with the smallest p, would be exactly the post-hoc significance hunting the pre-registration exists to prevent. No such analysis was run.

### 8.4 Power

With 36 paired items at α = 0.05 and 80% power, the **minimum detectable risk difference is ≈0.256** (normal approximation, assumed discordance 0.3).

Every observed difference in §8.2 is smaller than that. **These null results mean "this study could not detect an effect of this size", not "there is no effect."** The largest observed difference, baseline vs self-critique at 0.139, is about half the detectable threshold.

The primary comparison rests on **two discordant pairs**. Exact McNemar cannot return p < 0.05 with fewer than five, so under this design the primary test could not have been significant unless the reprompt control and self-critique had disagreed on at least five items. That is a design limitation, and it was foreseeable from the pilot's five baseline errors.

---

## 9. Failure analysis

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

Two categories deserve comment.

**`false_detection_survived` (15).** The model declared a *correct* answer incorrect, then kept it anyway. Its stated assessment and its behaviour came apart, and the behaviour was the reliable one. Since these never became false corrections, a study reading only final accuracy would not see them at all.

**`confident_persistence_of_error` (4).** A wrong answer was retained *and* affirmed as correct. Combined with §7.5 — stated confidence 100 on 215 of 216 trials — the stated assessment channel is close to uninformative on this model under this configuration.

The full classification, with examples selected by fixed rule rather than by inspection, is in [`../analysis/failure_analysis.md`](../analysis/failure_analysis.md).

`analysis/failure_analysis.py` classifies **every** trial into one of nine mutually exclusive categories by a deterministic rule, so counts sum to the total and no failure is reported without its denominator. Qualitative examples are selected by a fixed rule (first N by sorted task id), **not** by inspection — cherry-picking failures is the standard way a failure analysis becomes rhetoric rather than evidence.

Categories: `unparseable_response`, `confident_persistence_of_error`, `silent_persistence_of_error`, `detected_but_uncorrected`, `false_correction`, `false_detection_survived`, `successful_correction`, `stable_correct`, `other`.

---

## 10. What did not work

Recorded before any model run. This section will be extended with negative and null results from the actual experiment.

### 10.1 A specified condition was discarded

The original design listed **"F. Increased Task Difficulty"** as a sixth condition alongside the interventions. This is a category error: difficulty is an orthogonal *factor*, crossed with every condition, not a condition itself. Keeping it would have confounded difficulty with intervention type and made the study's central question — does the self-critique effect change with difficulty? — unanswerable.

It was removed before piloting and replaced with the reprompt control, which fills a genuine gap. Recorded as a dated addendum in [`hypotheses.md`](hypotheses.md#addenda) rather than silently applied.

### 10.2 Three implementation bugs that would have corrupted results

Reported because they are the kind of defect that produces confident, wrong findings rather than visible failures.

1. **Non-reproducible dataset generation.** Per-item seeds initially derived from Python's builtin `hash()`, which CPython salts per process unless `PYTHONHASHSEED` is pinned. Dataset generation would have been silently machine- and run-dependent while the code claimed reproducibility. Fixed with SHA-256; a test now generates under three different `PYTHONHASHSEED` values and asserts identical output.

2. **Cache poisoning across providers.** The mock provider originally wrote cache entries keyed identically to real calls. A mock run followed by a real run would have served synthetic responses as model output — producing a complete, plausible, entirely fabricated result set. The cache is now namespaced by provider, with a regression test asserting a real call is not served from a mock entry.

3. **Silent data loss in the parser.** The confidence regex did not tolerate markdown emphasis *after* the colon, so `**CONFIDENCE:** 75` parsed the answer but dropped the confidence. Since confidence is optional, this would have degraded the calibration analysis silently rather than raising. Caught by a unit test.

### 10.3 Anticipated weaknesses, and how they turned out

Each was written down before the run. All three held.

- *Response consistency at temperature 0 measures API determinism, not behavioural variability.* **Confirmed:** 12/12 agreement, no disagreements. Uninformative as a variability measure, though it does rule out sampling noise as an explanation for the condition differences.
- *Condition R controls for turn count but not for evaluative framing.* **This became the study's central interpretive limit.** R recovered 3 of 5 errors with no evaluative content, and R vs B was not distinguishable. The design can separate the critique from the extra turn only if the two differ by enough items to detect, and they did not.
- *The study is underpowered by design, given the free-tier budget.* **Confirmed, and worse than anticipated:** the pre-registration expected low power from n; the realized limit was five baseline errors, which is far more binding.

### 10.4 Two pilots produced no usable data

Pilots 1 and 2 both scored 48/48 at stage 1 — 96 live calls, roughly a quarter of the study's total budget, that yielded no measurable behaviour. Pilot 2's redesign raised reasoning depth substantially and still produced zero errors, which is what motivated changing the task type rather than scaling further ([Addendum 4](hypotheses.md#addenda)).

The gate did its job: it blocked the main run twice, and the main experiment was only funded once an instrument existed that could produce errors. The cost of that discipline was real, and the alternative — spending the full budget on a saturated instrument — would have produced a confident, empty result set.

---

## 11. Experimental accounting incident

Reported in full because a budget that is quietly exceeded is not a budget, and because the failure mode is instructive.

| | |
|---|---|
| Approved research cap | **370 API requests** |
| Actual cumulative usage | **389 API requests** |
| Overrun | **19 requests (5.1%)** |
| Logical calls in the main run | **240** |
| HTTP requests those calls issued | **259** |
| Retried calls | **19** |

**What happened.** The main run planned and issued exactly the 240 logical calls it was approved for. Nineteen of those calls hit transient provider errors and succeeded on a retry, so 259 HTTP requests were sent. Cumulative usage across the whole study reached 389 against a cap of 370.

**Root cause.** Two counters that should have agreed did not. `BudgetGuard.check()` compared *logical calls* against the cap, while the persistent ledger correctly debited *HTTP requests*. The guard therefore waved through 259 requests against a 240 ceiling and never signalled a breach. The ledger recorded the overrun accurately — it was the detection mechanism, not the enforcement one. Enforcement was counting the wrong unit.

**What was not affected.** No additional experimental conditions, tasks, prompts or analyses were run, intentionally or otherwise. The 19 extra requests are retries of approved calls that returned no new data: a retry that succeeds replaces a failure, it does not add a trial. Trial count, conditions, task set and every number in §7 and §8 are exactly what the pre-registered design specified. All usage remained on the free tier; no billing was enabled and no paid tier was used.

**Fix.** `BudgetGuard.check()` and `remaining()` now count `api_requests`. A residual overshoot bounded by one call's retry limit remains possible, because a call already in flight can retry after its own check has passed; bounding it to zero would mean reserving the full retry allowance for every call and leaving most of it unused. That trade-off is deliberate and documented in the code.

**Regression tests.** `tests/test_resume.py::TestGuardCountsRequestsNotCalls` asserts that retried calls consume the cap and that `remaining()` is reported in requests. `tests/test_ledger.py` covers cross-process accumulation, diagnostic-call inclusion, failed-call debiting, and the audited cap change.

**Disclosure standard.** The overrun is left visible in `experiments/budget_ledger.json` rather than reconciled away. The ledger currently reads 389 spent against a 370 cap, so any further run refuses to start — which is the correct end state for a closed study.

---

## 12. Discussion

### What the experiment demonstrates

On this 36-item task set, with this model and configuration:

- Baseline accuracy was 0.861, with five first-pass errors concentrated in `instruction_conflict`.
- Every intervention corrected some of those five errors and **none broke a correct answer** (false correction 0/31 in all six conditions). The pressure conditions did not induce sycophantic flipping.
- Format compliance was perfect (36/36) in every condition, and decoding was deterministic (12/12 on repeat).
- **No pre-registered comparison reached significance after correction.**

### What it merely suggests

The ordering — self-critique 5/5, conflicting evidence and preserve pressure 4/5, reprompt control and verification 3/5 — is consistent with self-critique being the most effective intervention. It is **not** evidence for that. Five errors cannot separate five conditions, the corrections are drawn from the same items, and the primary test rests on two discordant pairs.

**The neutral reprompt control is the finding that matters most here.** It corrected 3 of the same 5 errors while adding a turn and *no evaluative content whatsoever* — its prompt simply asks the model to state its final answer. Whatever mechanism recovered those three errors, it cannot have been critique, because no critique was requested. Self-critique recovered two more, and the difference between the two conditions is not statistically distinguishable (p_holm = 0.500).

So a substantial part of what would conventionally be reported as a "self-critique gain" is, in this data, reproduced by merely asking again. Had this study followed the common practice of comparing baseline against self-critique alone, it would have reported a 0.861 → 1.000 improvement and attributed it to the critique. The turn-matched control is what prevents that. This is consistent with Stechly et al., who found critique *content* largely irrelevant to whether iterative prompting helped ([arXiv:2310.12397](https://arxiv.org/abs/2310.12397)).

**This study does not establish that self-critique improves performance or alignment.** It is compatible with self-critique helping, with additional interaction alone helping, and with both.

### What it cannot establish

Anything about alignment as such. Anything about other models, configurations, or prompt phrasings. Anything about internal states — `false_detection_survived` (15) measures a stated claim, not a detection event.

The drop from 12/12 at d1 to 8/12 at d3 cannot be attributed to a safety property degrading rather than to the task simply being harder. **This design cannot separate capability from alignment**, and the difficulty ladder was never validated at adequate n.

Nor can it establish anything about the three families that sat at ceiling. `false_premise` and `convention` produced zero baseline errors on this model; whether they discriminate on a weaker one is untested.

---

## 13. Limitations

1. **n = 36, and only 5 baseline errors.** Every correction measure rests on those five. The minimum detectable difference is ≈0.26; every observed difference is smaller. Per-cell numbers are descriptive only.
2. **The error signal comes from one family.** Four of five baseline errors were `instruction_conflict`; the other three families were at or near ceiling, so the study is effectively one discriminating family plus three that did not discriminate on this model.
3. **The prompt ablation carries no information.** All 12 ablation items were already correct at stage 1, leaving nothing to correct and no discordant pairs.
4. **One model, one configuration**, thinking tokens disabled — and not the model the design was written against, since the original was withdrawn from new keys mid-study.
5. **Synthetic, narrow tasks** with single short verifiable answers.
6. **One prompt phrasing per condition**, with only the self-critique wording ablated, despite documented format sensitivity ([arXiv:2310.11324](https://arxiv.org/abs/2310.11324)).
7. **Calibration is unavailable, not weak.** Stated confidence took one value on 215 of 216 trials; ECE was gated off, as pre-registered.
8. **Response consistency at temperature 0** measures determinism, not variability.
9. **Statistical power is low**; non-significant results mean "underpowered," not "no effect." The primary comparison rests on two discordant pairs.

## 14. Threats to validity

**Internal.** Stage-1 sharing means a single bad initial answer propagates to all six conditions for that task — this strengthens pairing but correlates errors across conditions. Unparseable stage-1 responses drop the whole task, which could bias the retained set if unparseability correlates with difficulty; the rate is reported per condition and per difficulty.

**Construct.** The four properties are proxies, not definitions. Instruction consistency measures output *format* compliance, a deliberately narrow construct. "Error detection" measures a stated claim, not an internal detection event.

**External.** One model, one prompt set, one task style, one decoding configuration. Chance baselines differ across families (≈0 for arithmetic vs 0.25 for others at L1), so aggregate accuracy mixes different guess floors; per-family results are reported separately.

**Statistical.** Multiple comparisons are Holm-corrected within the pre-registered family only; secondary analyses are uncorrected and labelled as such. Bootstrap intervals on rates with denominators in the single digits are wide and should not be over-read.

**Ceiling/floor.** If accuracy sits at ceiling on L1 or floor on L3, correction denominators become degenerate. The pilot checks this before the main budget is spent.

---

## 15. Future research

- Temperature > 0 to measure genuine sampling-induced consistency.
- Thinking tokens enabled, to compare visible- and hidden-reasoning self-correction.
- Prompt ablation widened across all conditions, reporting ranges rather than point estimates.
- Substantially larger n.
- A stricter control isolating evaluative framing from critique.
- Injected *wrong* critiques, to test whether critique content matters at all ([arXiv:2310.12397](https://arxiv.org/abs/2310.12397)).

---

## 16. Conclusion

Across 36 tasks and 216 paired trials on `gemini-3.1-flash-lite`:

**Stable under the conditions tested.** Format compliance (36/36 everywhere) and resistance to breaking correct answers (false correction 0/31 in every condition, including both pressure conditions). Decoding was deterministic, 12/12.

**Not measurable.** Confidence calibration. Stated confidence was 100 on 215 of 216 trials, so the property could not be assessed at all — reported as unavailable rather than approximated.

**Not established.** Whether self-critique improves accuracy. Final accuracy was 36/36 under self-critique against 34/36 under a turn-matched neutral reprompt, and that difference is not statistically distinguishable (Holm-adjusted p = 0.500, two discordant pairs). The neutral control recovered 3 of the same 5 errors with no evaluative content at all, so additional interaction alone explains much of the apparent effect. **This study does not show that self-critique works.**

**Not tested.** Whether behavioural properties degrade differentially with difficulty (H1). Five errors, concentrated in one family, cannot support a dissociation claim.

The honest summary is that the instrument was made to work — after two pilots at ceiling and a change of task type — and then turned out to be too small to answer the question it was built for. A 36-item single-model study with five baseline errors can report what was observed and rule almost nothing out. Extending it would mean substantially larger n, which this budget did not allow.

---

## References

See [`background.md`](background.md#7-references) for the full reference list with arXiv links.
