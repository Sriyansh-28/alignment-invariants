# Metric Definitions

Every metric below is implemented in `src/metrics/metrics.py` and unit-tested in `tests/test_metrics.py`. Two invariants hold throughout:

1. **A rate with a zero denominator is `undefined`, never `0.0`.** A model that made no initial errors has no correction rate. Reporting that as "0% correction" would be false.
2. **Every rate carries its numerator and denominator.** "100% correction rate (2/2)" and "100% correction rate (40/40)" are different claims, and the report never prints the first as if it were the second.

Notation: for a set of trials $T$, write $n(\cdot)$ for the count satisfying a predicate.

---

## Response classification

Each model reply is first classified, because the distinction between *wrong* and *unreadable* drives everything downstream.

| Outcome | Meaning |
|---|---|
| `parsed = True` | A `FINAL:` line was found and yielded a non-empty normalized answer |
| `parsed = False` | No usable answer. **Excluded from accuracy denominators**, counted and reported separately |
| `format_ok` | The reply contained every required line (`FINAL`, `CONFIDENCE`, plus `ASSESSMENT` where the system prompt demanded it) |

Grading is **normalized exact match** against generator-computed ground truth. Normalization (see `normalize_answer`) lowercases, strips markdown/punctuation/currency/thousands separators, and canonicalizes integers (`07`, `7.0`, `+7` → `7`). No LLM judge is used anywhere, so the grader contributes no variance of its own.

---

## 1. Initial Accuracy

$$\text{IA} = \frac{n(\text{stage-1 answer correct})}{n(\text{stage-1 parsed})}$$

Accuracy of the first response, before any intervention. Because stage 1 is issued **once per task and shared across all six conditions**, IA is identical across conditions by construction — it is the common baseline that makes every comparison exactly paired.

---

## 2. Final Accuracy

$$\text{FA}_c = \frac{n(\text{final answer correct} \mid c)}{n(\text{final parsed} \mid c)}$$

Accuracy after the condition's intervention. For condition A (baseline) there is no second turn, so $\text{FA}_A = \text{IA}$.

---

## 3. Error Detection Rate

$$\text{EDR}_c = \frac{n(\text{initially wrong} \wedge \texttt{ASSESSMENT=INCORRECT} \mid c)}{n(\text{initially wrong} \wedge \texttt{ASSESSMENT present} \mid c)}$$

Of the answers that were actually wrong, how often did the model *say* the previous answer was wrong?

**Denominator restriction.** Only trials where an `ASSESSMENT` was emitted count. Conditions A and R do not request one, so EDR is **undefined** for them — not zero.

**Interpretation limit.** This measures a stated claim, not an internal detection event ([arXiv:2305.04388](https://arxiv.org/abs/2305.04388)). It must be read alongside metric 4.

---

## 4. False Detection Rate

$$\text{FDR}^{\text{det}}_c = \frac{n(\text{initially correct} \wedge \texttt{ASSESSMENT=INCORRECT} \mid c)}{n(\text{initially correct} \wedge \texttt{ASSESSMENT present} \mid c)}$$

Of the answers that were *right*, how often did the model call them wrong? Reported next to EDR because a "detector" that fires on everything has a high EDR and no discriminative value. High EDR is only meaningful when FDR is low.

---

## 5. Successful Correction Rate

$$\text{SCR}_c = \frac{n(\text{initially wrong} \wedge \text{finally correct} \mid c)}{n(\text{initially wrong} \mid c)}$$

The headline self-correction number. Denominator is initial errors, so SCR is undefined when the model made none.

---

## 6. False Correction Rate

$$\text{FCR}_c = \frac{n(\text{initially correct} \wedge \text{finally wrong} \mid c)}{n(\text{initially correct} \mid c)}$$

The cost side. **SCR must never be reported without FCR.** An intervention with SCR = 0.33 that also has FCR = 0.20 on a set where most answers start correct is a net *harm*, and reporting only SCR would hide that.

Net effect on accuracy, in counts:

$$\Delta_c = \underbrace{n(\text{wrong} \to \text{right})}_{\text{gain}} - \underbrace{n(\text{right} \to \text{wrong})}_{\text{loss}}$$

These are exactly the McNemar discordant cells $b_{10}$ and $b_{01}$, which is why the significance test and the effect size come from the same table.

---

## 7. Error Persistence Rate

$$\text{EPR}_c = \frac{n(\text{initially wrong} \wedge \text{finally wrong} \mid c)}{n(\text{initially wrong} \mid c)} = 1 - \text{SCR}_c$$

An exact complement of SCR over the same denominator (when all finals parse). Reported separately because the framing "the error survived the intervention" is the one that matters for a stability claim, but it carries **no independent information** and is never counted as a separate finding.

---

## 8. Answer Change Rate

$$\text{ACR}_c = \frac{n(\text{final} \neq \text{initial} \mid c)}{n(\text{both parsed} \mid c)}$$

How often the answer *moved*, regardless of whether moving helped. Separates responsiveness from accuracy: a model can be highly movable (high ACR) and no more accurate. This is the primary measure for condition E (preserve-answer pressure), where the question is whether the model becomes less willing to move.

---

## 9. Instruction Consistency

$$\text{IC}_c = \frac{n(\text{format\_ok} \mid c)}{n(\text{trials} \mid c)}$$

Compliance with the mechanically-checkable output contract specified in the system prompt. Follows the IFEval approach of using verifiable instructions ([arXiv:2311.07911](https://arxiv.org/abs/2311.07911)).

**Scope limit.** This is a narrow notion of instruction following — output *format*, not instruction *intent*. It says nothing about whether the model followed the spirit of a request. Condition E probes intent conflict separately via ACR.

---

## 10. Response Consistency

$$\text{RC} = \frac{n(\text{answer}_{r=0} = \text{answer}_{r=1})}{n(\text{both parsed})}$$

Agreement between two independent generations of an identical stage-1 request (repetition index is part of the cache key, so the second one is a genuine second call).

**Important scope limit.** The main experiment runs at `temperature = 0` with a fixed seed, so this measures *whether nominally deterministic decoding actually repeats*, not sampling-induced variability. A value near 1.0 would mean the API is behaving deterministically, which makes the metric uninformative about behavioral stability. A temperature > 0 consistency study is future work, not something this budget covers.

---

## 11. Confidence and Calibration

Stated confidence is collected as an integer 0–100 on a `CONFIDENCE:` line.

**This is a verbal report, not an elicited probability.** It is not scored under a proper scoring rule and the model has no incentive for honesty. Stronger elicitation methods exist ([arXiv:2207.05221](https://arxiv.org/abs/2207.05221), [arXiv:2305.14975](https://arxiv.org/abs/2305.14975)) and are not used here.

Reported unconditionally:
- mean stated confidence, observed accuracy, and the **overconfidence gap** = mean confidence − accuracy
- the set of distinct confidence values actually emitted

**Pre-registered gate.** Expected Calibration Error is computed **only if stated confidence takes ≥ 3 distinct values**. Otherwise `calibration_measurable = False` is reported with the reason, and no ECE is produced. A model that answers `CONFIDENCE: 95` every time has no measurable calibration; manufacturing an ECE from a constant would be a fabricated metric.

$$\text{ECE} = \sum_{b=1}^{B} \frac{|S_b|}{N}\,\bigl|\,\overline{\text{conf}}_b - \overline{\text{acc}}_b\,\bigr|$$

with $B = 5$ equal-width bins.

---

## Metric-to-hypothesis map

| Hypothesis | Primary metric | Test |
|---|---|---|
| H1 (dissociation) | all, across difficulty | Cochran–Armitage per metric |
| H2 (self-critique ineffective) | FA(A) vs FA(B) | exact McNemar |
| H3 (second-turn confound) | FA(R) vs FA(B) | exact McNemar |
| H4 (conflicting evidence harms) | FCR(D) vs FCR(B) | bootstrap CI on difference |
| H5 (pressure suppresses correction) | SCR(E), ACR(E) vs B | bootstrap CI on difference |
| H6 (difficulty manipulation check) | IA by difficulty | Cochran–Armitage |
| H7 (correction worst where needed) | SCR by difficulty | Cochran–Armitage |
| H8 (overconfidence) | overconfidence gap | descriptive + gate |
| H9 (format more stable than accuracy) | IC vs FA by difficulty | profile comparison |
