# Alignment Invariants Under Capability and Behavioral Pressure

**Status: experiments pending.** Design, implementation, and analysis code are complete and tested. No live model run has been executed, so every results section below is a placeholder. **No number in this document is estimated, projected, or written by hand** — results sections will be populated from `results/tables/summary.json` after a real run.

---

## Abstract

*To be written after the experiment.* The abstract will state what was measured, on how many items, with what statistical support, and — explicitly — what the result does not establish. It will not be drafted in advance, because writing an abstract before seeing data invites fitting the narrative to the hypothesis.

**Pre-registered design summary.** A single Gemini model is evaluated on 27 procedurally generated reasoning tasks spanning three structurally-defined difficulty levels, under six conditions: baseline, a neutral reprompt control, self-critique, verification, conflicting evidence, and preserve-answer pressure. All interventions act on the same stage-1 answer, making comparisons exactly paired. The study measures whether four candidate behavioral properties — self-correction, instruction consistency, robustness to misleading information, and confidence/correctness correspondence — remain stable as difficulty and pressure increase.

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

Within-model, fully paired. 27 tasks × 6 conditions, with difficulty (3 levels) and task family (3) crossed.

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

One model (`GEMINI_MODEL`, default `gemini-2.5-flash`), `temperature = 0`, fixed seed, `max_output_tokens = 1024`, **thinking tokens disabled**.

Disabling hidden reasoning is deliberate: with it enabled the model may self-correct internally, confounding condition B. The cost is that findings describe the non-thinking configuration only.

### 5.3 Task construction

Procedurally generated (see [`../data/README.md`](../data/README.md)). Three families: `arith_chain`, `logic_order`, `set_filter`. Chosen for contamination control, exact ground truth computed by the generating code, and difficulty as a generator parameter rather than a human label.

Ground truth is never produced by an LLM judge, so the grader contributes zero variance. Grading is normalized exact match.

Difficulty varies operation count, chain depth, predicate count, and distractor count, with the surface template held constant within a family. Each task carries a `distractor_answer` derived from a *named reasoning slip*, so conditions D and E apply comparably plausible pressure at every level.

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

Hard cap of 250 live calls, enforced at call time and by pre-flight schedule checking. Planned: pilot 48 + main 186 = 234. Every response is cached and the cache is committed, so all results are reproducible without a key.

---

## 6. Experimental setup

**Experiments pending.** This section will record the exact model string, run timestamps, realized call counts (total / cached / successful / failed / per condition), and token usage, read from the run's `meta.budget` block.

---

## 7. Results

**Experiments pending.**

Will contain: initial accuracy with Wilson intervals; per-condition final accuracy; correction, false-correction, persistence, and answer-change rates with bootstrap intervals; instruction consistency; response consistency; and the difficulty breakdown — all generated from `results/tables/summary.json`.

---

## 8. Statistical analysis

**Experiments pending.**

Will report the Cochran's Q omnibus, the five pre-registered pairwise McNemar tests with raw and Holm-adjusted p-values, paired difference confidence intervals, difficulty trend tests, and the minimum detectable effect.

---

## 9. Failure analysis

**Experiments pending.**

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

### 10.3 Anticipated methodological weaknesses

- Response consistency at temperature 0 measures API determinism, not behavioral variability. The metric is retained but is expected to be uninformative, and is reported as such.
- Condition R controls for turn count but not for evaluative framing.
- The study is underpowered by design, given the free-tier budget.

---

## 11. Discussion

**Experiments pending.**

This section will explicitly separate three things:

**What the experiment demonstrates** — direct measurements on this task set under these conditions, with intervals.

**What it merely suggests** — patterns consistent with the data but not established by it, especially anything resting on small denominators or per-cell counts.

**What it cannot establish** — anything about alignment as such; anything about other models, other configurations, or other prompt phrasings; anything about internal states. A drop at difficulty 3 cannot be attributed to a "safety property degrading" rather than to the task simply being harder — this study cannot separate capability from alignment.

The study will not claim to prove alignment or misalignment. The appropriate conclusion may be simply that a given property was, or was not, stable under the conditions tested.

---

## 12. Limitations

1. **n = 27** — 9 per difficulty level, 3 per family-difficulty cell. Per-cell numbers are descriptive only.
2. **One model, one configuration**, thinking tokens disabled.
3. **Synthetic, narrow tasks** with single short verifiable answers.
4. **One prompt phrasing per condition**, with only the self-critique wording ablated, despite documented format sensitivity ([arXiv:2310.11324](https://arxiv.org/abs/2310.11324)).
5. **Stated confidence is a verbal report**, not an elicited probability. ECE is gated on ≥3 distinct values.
6. **Response consistency at temperature 0** measures determinism, not variability.
7. **Statistical power is low**; non-significant results mean "underpowered," not "no effect."

## 13. Threats to validity

**Internal.** Stage-1 sharing means a single bad initial answer propagates to all six conditions for that task — this strengthens pairing but correlates errors across conditions. Unparseable stage-1 responses drop the whole task, which could bias the retained set if unparseability correlates with difficulty; the rate is reported per condition and per difficulty.

**Construct.** The four properties are proxies, not definitions. Instruction consistency measures output *format* compliance, a deliberately narrow construct. "Error detection" measures a stated claim, not an internal detection event.

**External.** One model, one prompt set, one task style, one decoding configuration. Chance baselines differ across families (≈0 for arithmetic vs 0.25 for others at L1), so aggregate accuracy mixes different guess floors; per-family results are reported separately.

**Statistical.** Multiple comparisons are Holm-corrected within the pre-registered family only; secondary analyses are uncorrected and labelled as such. Bootstrap intervals on rates with denominators in the single digits are wide and should not be over-read.

**Ceiling/floor.** If accuracy sits at ceiling on L1 or floor on L3, correction denominators become degenerate. The pilot checks this before the main budget is spent.

---

## 14. Future research

- Temperature > 0 to measure genuine sampling-induced consistency.
- Thinking tokens enabled, to compare visible- and hidden-reasoning self-correction.
- Prompt ablation widened across all conditions, reporting ranges rather than point estimates.
- Substantially larger n.
- A stricter control isolating evaluative framing from critique.
- Injected *wrong* critiques, to test whether critique content matters at all ([arXiv:2310.12397](https://arxiv.org/abs/2310.12397)).

---

## 15. Conclusion

**Experiments pending.**

The conclusion will state which properties were and were not stable under the conditions tested, with the sample size and interval width attached to every claim, and will not extend beyond what a 27-item single-model study can support.

---

## References

See [`background.md`](background.md#7-references) for the full reference list with arXiv links.
