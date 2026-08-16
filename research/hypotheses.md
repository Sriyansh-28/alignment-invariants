# Hypotheses (pre-registered)

**Status: written before any experimental API call was made.**

This document is committed prior to the main run and is not edited afterwards. If the pilot forces a design change, the change is recorded in a dated addendum at the bottom rather than by rewriting the hypotheses. Any analysis not listed here is exploratory and is labelled as such in the report.

Design in one line: 27 procedurally generated tasks × 3 difficulty levels × 6 conditions, single model, all interventions applied to the *same* stage-1 answer so comparisons are exactly paired.

---

## Primary hypothesis

**H1.** Alignment-relevant behavioral properties do not all scale monotonically with task difficulty and behavioral pressure. Different properties degrade or improve at different rates.

H1 is a *dissociation* claim, not a direction claim. It is supported if the properties measured (accuracy, self-correction efficacy, pressure-resistance, format compliance) show materially different profiles across the difficulty ladder. It is not supported if they all move together, or all stay flat.

**Operational test.** For each property, estimate its value at difficulty 1, 2, 3 with Wilson intervals, and test for trend with Cochran–Armitage. H1 gains support if at least one property shows a significant trend while at least one other does not, *and* the difference in profile is not attributable to differing measurement precision.

**Honest caveat stated in advance:** with n = 27 (9 per difficulty level), this test is weak. A null result here is much more likely to reflect low power than genuine invariance, and will be reported that way. See "Power" below.

---

## Secondary hypotheses

**H2 — Self-critique does not reliably improve accuracy.**
Prior work ([arXiv:2310.01798](https://arxiv.org/abs/2310.01798), [arXiv:2406.01297](https://arxiv.org/abs/2406.01297)) predicts intrinsic self-correction fails without external feedback. Predicted: accuracy under condition B is not significantly higher than under A, and may be lower.

**H3 — Any apparent self-critique effect is partly a second-turn effect.**
The comparison that matters is B vs **R** (neutral reprompt), not B vs A. Predicted: some of the A→B change is reproduced by A→R, meaning the critique-specific effect is smaller than the naive A vs B contrast suggests.
*This is the hypothesis the reprompt control exists to test, and the one most likely to produce a novel result.*

**H4 — Conflicting evidence degrades accuracy more than self-critique does.**
Given documented sycophancy ([arXiv:2310.13548](https://arxiv.org/abs/2310.13548)), asserting a specific plausible wrong answer (condition D) should move the model off correct answers. Predicted: false correction rate under D > under B.

**H5 — Preserve-answer pressure suppresses correction.**
Condition E instructs the model not to change an answer, in tension with the system instruction to answer correctly. Predicted: successful correction rate under E < under B, and answer change rate under E < under B.

**H6 — Initial accuracy declines monotonically across the difficulty ladder.**
This is a manipulation check, not a finding. If it fails, the difficulty construction did not work and the difficulty-related analyses are uninterpretable.

**H7 — Self-correction efficacy is worse where it is needed most.**
Predicted: successful correction rate is lower at difficulty 3 than at difficulty 1. If a model can only fix errors on problems it was likely to get right anyway, self-correction is weakest exactly where it would matter.

**H8 — Stated confidence exceeds accuracy (overconfidence).**
Predicted: mean stated confidence > observed accuracy, with the gap widening at higher difficulty.
*Pre-registered abort condition:* if stated confidence takes fewer than 3 distinct values across the run, no calibration metric will be computed, and this will be reported as a measurement failure rather than as a finding. Verbal confidence is a stated report, not an elicited probability.

**H9 — Format compliance (instruction consistency) is more stable than accuracy.**
Predicted: format compliance stays near ceiling across all difficulties and conditions while accuracy falls. If so, that is a within-model dissociation supporting H1.

---

## Null hypotheses

Stated explicitly so that failing to reject them is a reportable outcome, not a gap.

- **H0-1.** All measured properties share the same profile across difficulty; no dissociation.
- **H0-2.** Accuracy under B equals accuracy under A (no self-critique effect).
- **H0-3.** Accuracy under B equals accuracy under R (no critique-specific effect beyond a second turn).
- **H0-4.** False correction rate is equal under D and B.
- **H0-5.** Successful correction rate is equal under E and B.
- **H0-6.** Initial accuracy is constant across difficulty levels.
- **H0-7.** Successful correction rate is constant across difficulty levels.
- **H0-8.** Mean stated confidence equals observed accuracy.
- **H0-9.** Format compliance and accuracy have the same profile across difficulty.

---

## Pre-registered analysis plan

**Primary comparison family** (Holm–Bonferroni corrected, α = 0.05, family size 5):

| # | Comparison | Test |
|---|---|---|
| 1 | A vs R | exact McNemar |
| 2 | A vs B | exact McNemar |
| 3 | R vs B | exact McNemar |
| 4 | A vs D | exact McNemar |
| 5 | A vs E | exact McNemar |

Cochran's Q across all six conditions is run **first** as an omnibus test. The pairwise family is interpreted in light of it.

**Secondary analyses** (reported with uncorrected p-values, explicitly labelled secondary):
- Cochran–Armitage trend across difficulty, per condition and per metric.
- B vs C (self-critique vs verification).
- B vs B-alt (prompt-wording ablation, subset of 12).
- Per-family breakdown (arith / logic / set-filter).

**Estimation.** Every rate is reported with numerator, denominator, and a Wilson interval. Rates with random denominators (correction rates) get percentile bootstrap intervals clustered on task.

**Exclusions, decided in advance.**
- Unparseable responses are excluded from accuracy denominators and counted separately. They are never scored as errors.
- A trial whose stage-1 response was unparseable is dropped from all conditions, since there is no initial answer for the intervention to act on.
- No task is excluded on the basis of its result.

**Power.** With 27 paired items, the minimum detectable risk difference at 80% power (α = 0.05, assuming ~30% discordance) is roughly 0.2 in absolute accuracy. Effects smaller than that will not be detectable. This is computed explicitly in `analysis/statistical_tests.py::mde_paired` and reported alongside every null result. **Any non-significant result in this study should be read as "underpowered to detect," not as "no effect."**

**Stopping rule.** Total live API calls are hard-capped at 250. The pilot (≤50 calls) gates the main run: if the pilot shows a design defect, the design is fixed before the remaining budget is spent, and the change is recorded as an addendum here.

---

## What this study cannot establish

Stated in advance to constrain the conclusions:

1. It cannot show that the model is or is not "aligned." The properties measured are candidate proxies chosen for measurability, not a definition of alignment.
2. It cannot separate capability from alignment. A drop at difficulty 3 may simply mean the task got harder.
3. It cannot generalize across models. One model, one configuration (thinking tokens disabled), one prompt set.
4. It cannot generalize across prompt phrasings beyond the single wording ablation run here — a real limitation given documented format sensitivity ([arXiv:2310.11324](https://arxiv.org/abs/2310.11324)).
5. It cannot measure internal states. A stated `ASSESSMENT` is an output, not evidence about an internal error signal ([arXiv:2305.04388](https://arxiv.org/abs/2305.04388)).
6. With n = 27 it cannot support confident claims about small effects in either direction.

---

## Addenda

Any design change forced by the pilot is recorded here, dated, with the reason.

### Addendum 1 — pre-run design decision (before any API call)

The condition list originally specified in the project brief included **"F. Increased Task Difficulty"** as a sixth experimental condition alongside Baseline, Self-Critique, Verification, Conflicting Evidence, and Misleading Instruction.

This was removed before piloting, because it is not a condition. Difficulty is an orthogonal *factor* that is crossed with every condition — every task already carries a difficulty level, and all six conditions are run at all three levels. Treating difficulty as a sixth condition would have made it impossible to ask the question the study is actually about ("does the effect of self-critique change with difficulty"), because difficulty would have been confounded with intervention type.

It was replaced with **R. Reprompt control**, a content-neutral second turn, which fills a genuine gap: without it, every intervention effect is confounded with turn count.

This is recorded here rather than silently applied. It is discussed in "What Did Not Work" in the report.
