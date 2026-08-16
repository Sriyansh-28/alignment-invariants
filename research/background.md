# Background and Related Work

Every claim below is tagged:

- **[ESTABLISHED]** — reported in peer-reviewed or widely-replicated work, and not seriously contested.
- **[HYPOTHESIS]** — a plausible claim with some supporting evidence, actively debated or not yet settled.
- **[SPECULATION]** — a conceptual framing or extrapolation. Not evidence. Flagged so it is not mistaken for a finding.

Citations are given with arXiv identifiers and links. Nothing in this document paraphrases text from the cited papers beyond what is needed to state their claims.

---

## 1. Motivation

The alignment problem is usually posed as a question about *systems that do not yet exist*: will a more capable model continue to behave as intended? That framing makes empirical work awkward, because the object of study is in the future.

One tractable move is to stop asking whether a model "is aligned" and instead ask a narrower, measurable question: **which behavioral properties of a model stay put when conditions get harder, and which ones move?**

This project calls such candidate properties *alignment invariants*. The term is used here descriptively, not as a claim that the properties measured are necessary or sufficient for alignment.

**[SPECULATION]** A property that survives easy conditions but collapses under difficulty or pressure is a poor foundation for a safety argument, because deployment conditions are rarely the easy ones. This is the intuition motivating the study. It is a framing, not a result, and this experiment does not test it directly.

The four candidate properties studied here:

1. **Self-correction** — does the model repair its own errors when prompted to review?
2. **Instruction consistency** — does it keep following the stated output contract?
3. **Robustness to misleading information** — does a confident wrong assertion from an apparent third party move it off a correct answer?
4. **Confidence/correctness correspondence** — does stated confidence track being right?

---

## 2. What is established

### 2.1 Intrinsic self-correction does not reliably work

**[ESTABLISHED]** Prompting a model to review and revise its own reasoning, *with no external feedback*, does not reliably improve accuracy and can reduce it. Huang et al. tested this directly and found performance degrading after self-correction on reasoning benchmarks ([arXiv:2310.01798](https://arxiv.org/abs/2310.01798)).

**[ESTABLISHED]** The critical variable is the quality of the feedback signal, not the act of revising. Kamoi et al.'s survey concludes that self-correction succeeds when there is reliable *external* feedback or targeted fine-tuning, and largely fails when the model must supply its own critique ([arXiv:2406.01297](https://arxiv.org/abs/2406.01297)).

**[ESTABLISHED]** Stechly et al. found that on graph colouring, the *content* of the critique was largely irrelevant to whether iterative prompting helped — improvements traced to correct answers already present in the sampled outputs rather than to genuine self-verification ([arXiv:2310.12397](https://arxiv.org/abs/2310.12397)).

This matters because a well-known earlier result pointed the other way. Self-Refine reported roughly 20% absolute average improvement from iterative self-feedback ([arXiv:2303.17651](https://arxiv.org/abs/2303.17651)). The tension between these results is largely about task type and whether the evaluation had access to ground truth. **[HYPOTHESIS]** Self-correction helps on tasks where verification is easier than generation, and hurts where it is not.

This experiment is designed so that it *can* come out either way. It does not assume self-correction is beneficial.

### 2.2 Models are sycophantic

**[ESTABLISHED]** Language models trained on human preference data tend to agree with the user rather than maintain a correct position. Sharma et al. document this across several production assistants and trace it to human preference data, where raters favour responses matching their own stated views ([arXiv:2310.13548](https://arxiv.org/abs/2310.13548)).

This is the most direct prior work for conditions D and E here. It predicts that asserting a wrong answer should move the model.

### 2.3 Stated reasoning is not always the operative reasoning

**[ESTABLISHED]** Turpin et al. showed that chain-of-thought explanations systematically omit the factors actually driving the answer; biasing features changed answers by up to 36% on some benchmarks without ever being mentioned in the explanation ([arXiv:2305.04388](https://arxiv.org/abs/2305.04388)).

This is a direct constraint on the present study's design: a model's stated self-assessment ("ASSESSMENT: INCORRECT") is a *behavioral output*, not a window into an internal error signal. This study measures the former and makes no claim about the latter.

### 2.4 Calibration is real but the measurement method matters

**[ESTABLISHED]** Larger models can be well calibrated when self-evaluating in an appropriate format; Kadavath et al. showed models predicting the probability their own answers are correct, with calibration improving with scale ([arXiv:2207.05221](https://arxiv.org/abs/2207.05221)).

**[ESTABLISHED]** Verbalized confidence elicited as output tokens can be better calibrated than the model's own conditional probabilities in RLHF-tuned models, though this is method-sensitive ([arXiv:2305.14975](https://arxiv.org/abs/2305.14975)).

**[HYPOTHESIS]** A single unincentivized "CONFIDENCE: 0-100" line, as used here, is a much weaker elicitation than either of the above. It is not scored under a proper scoring rule and the model has no incentive to be honest. This study therefore treats stated confidence as a *verbal report* and refuses to compute calibration metrics if the distribution turns out to be degenerate. See §11 of the report.

### 2.5 Behaviour is highly sensitive to surface prompt form

**[ESTABLISHED]** Sclar et al. found accuracy differences up to 76 percentage points from formatting changes alone, and recommend reporting performance *ranges* over prompt variants rather than single numbers ([arXiv:2310.11324](https://arxiv.org/abs/2310.11324)).

This is why this study includes a prompt-wording ablation (condition B vs B-alt) rather than treating one phrasing of "self-critique" as *the* self-critique intervention. It is also the main reason to be cautious about generalizing any effect found here.

### 2.6 Instruction following is measurable when instructions are verifiable

**[ESTABLISHED]** IFEval established the practical approach of using *programmatically verifiable* instructions ("write in under N words") to avoid the expense and irreproducibility of human judgment ([arXiv:2311.07911](https://arxiv.org/abs/2311.07911)).

This study borrows that idea in miniature: the output-format contract (`ASSESSMENT` / `FINAL` / `CONFIDENCE` lines) is mechanically checkable, so instruction consistency is measured without a judge model.

### 2.7 Capable behaviour on a training distribution need not transfer

**[ESTABLISHED]** Goal misgeneralization: a system can competently pursue an unintended goal that was consistent with training performance but diverges out of distribution ([arXiv:2210.01790](https://arxiv.org/abs/2210.01790)).

**[SPECULATION]** The present study is *not* a test of goal misgeneralization, which is about learned objectives generalizing badly. It is cited only to situate the general worry that behaviour measured under benign conditions may not describe behaviour under other conditions. Conflating the two would be a category error.

### 2.8 The field lacks settled evaluation methodology

**[ESTABLISHED]** Anwar et al., surveying 18 foundational challenges in assuring LLM alignment and safety, identify evaluation methodology itself as an open problem ([arXiv:2404.09932](https://arxiv.org/abs/2404.09932)).

---

## 3. What remains uncertain

1. **[HYPOTHESIS]** Whether self-correction failure is a fixed property or a function of task difficulty. Most self-correction studies report an aggregate over a benchmark. If the failure is concentrated at particular difficulty levels, an aggregate number conceals it.

2. **[HYPOTHESIS]** Whether the *different* behavioral properties degrade together. If accuracy, format compliance, and pressure-resistance all fall off at the same rate, "capability" explains everything. If they dissociate, they are separate things to measure.

3. **[HYPOTHESIS]** Whether "self-critique" and "verify by re-deriving" are the same intervention. They are frequently used interchangeably in the literature, but they ask for different operations.

4. **[HYPOTHESIS]** How much of the reported benefit of any second-pass intervention is just the effect of a second pass. Most published comparisons contrast one-turn generation with a two-turn critique pipeline, which confounds the critique with the extra turn.

---

## 4. Research gap

The gap this study addresses is narrow and specific:

> Existing self-correction studies mostly report a single aggregate effect per benchmark, with no controlled difficulty ladder, and — critically — **usually without a turn-matched control condition**.

Two concrete design consequences follow:

**(a) A neutral reprompt control.** If baseline is one turn and self-critique is two, then any difference between them is a difference between "one pass" and "two passes plus a critique instruction." This study adds condition **R**, a content-neutral second turn ("state your final answer"), so the critique-specific effect can be separated from the second-pass effect. This is the main methodological contribution here, and it is cheap: one extra condition.

**(b) A structurally-defined difficulty ladder.** Difficulty is set by generator parameters (operation count, chain depth, predicate count), not by human labels, so "harder" means something specific and reproducible.

The study is small (27 items, one model). It is positioned as a careful *within-model* measurement, not a benchmark.

---

## 5. Relationship to prior evaluation approaches

| Approach | What it does | How this differs |
|---|---|---|
| Static benchmarks (GSM8K, MMLU) | Fixed public items, single-pass accuracy | Items are procedurally generated per-run, so contamination is controlled; the outcome of interest is the *change* across conditions, not the level |
| Self-Refine / Reflexion style | Show that iterative refinement improves a metric | Adds a turn-matched control; treats "no effect" and "harm" as reportable outcomes |
| Sycophancy evals | Measure agreement shift under user pressure | Pressure is task-derived (a specific wrong answer from a defined reasoning slip), held plausible across difficulty levels |
| IFEval | Verifiable instruction compliance at scale | Same verifiability idea, applied to a small output contract, measured *jointly* with accuracy under the same conditions |
| LLM-as-judge | Model grades model | Not used. Ground truth is computed by the generator, so the grader contributes no variance |

---

## 6. Why this experiment is useful

It is a small, honest measurement of something the literature has mostly reported in aggregate. Three specific things it can deliver that a headline accuracy number cannot:

1. **A dissociation test.** Do the four candidate properties move together or separately as difficulty rises?
2. **A decomposition of the self-correction effect.** How much is the critique and how much is just the second turn?
3. **A cost accounting.** False correction rate is reported alongside successful correction rate, so an intervention that fixes three errors while breaking four is visible as a net harm rather than as "33% correction rate."

**[SPECULATION]** If behavioral properties dissociate under pressure, then safety arguments that treat "the model is well-behaved" as a single property are on weaker ground than arguments that name and measure specific properties. This study cannot establish that; at most it can show a dissociation in one model on one task family.

---

## 7. References

All links verified at the time of writing.

- Amodei, D., Olah, C., Steinhardt, J., Christiano, P., Schulman, J., Mané, D. (2016). *Concrete Problems in AI Safety.* [arXiv:1606.06565](https://arxiv.org/abs/1606.06565)
- Anwar, U., Saparov, A., Rando, J., Paleka, D., Turpin, M., et al. (2024). *Foundational Challenges in Assuring Alignment and Safety of Large Language Models.* [arXiv:2404.09932](https://arxiv.org/abs/2404.09932)
- Huang, J., Chen, X., Mishra, S., Zheng, H. S., Yu, A. W., Song, X., Zhou, D. (2023). *Large Language Models Cannot Self-Correct Reasoning Yet.* [arXiv:2310.01798](https://arxiv.org/abs/2310.01798)
- Kadavath, S., Conerly, T., Askell, A., Henighan, T., et al. (2022). *Language Models (Mostly) Know What They Know.* [arXiv:2207.05221](https://arxiv.org/abs/2207.05221)
- Kamoi, R., Zhang, Y., Zhang, N., Han, J., Zhang, R. (2024). *When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of Self-Correction of LLMs.* [arXiv:2406.01297](https://arxiv.org/abs/2406.01297)
- Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., et al. (2023). *Self-Refine: Iterative Refinement with Self-Feedback.* [arXiv:2303.17651](https://arxiv.org/abs/2303.17651)
- Sclar, M., Choi, Y., Tsvetkov, Y., Suhr, A. (2023). *Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design.* [arXiv:2310.11324](https://arxiv.org/abs/2310.11324)
- Shah, R., Varma, V., Kumar, R., Phuong, M., Krakovna, V., Uesato, J., Kenton, Z. (2022). *Goal Misgeneralization: Why Correct Specifications Aren't Enough For Correct Goals.* [arXiv:2210.01790](https://arxiv.org/abs/2210.01790)
- Sharma, M., Tong, M., Korbak, T., Duvenaud, D., Askell, A., et al. (2023). *Towards Understanding Sycophancy in Language Models.* [arXiv:2310.13548](https://arxiv.org/abs/2310.13548)
- Stechly, K., Marquez, M., Kambhampati, S. (2023). *GPT-4 Doesn't Know It's Wrong: An Analysis of Iterative Prompting for Reasoning Problems.* [arXiv:2310.12397](https://arxiv.org/abs/2310.12397)
- Tian, K., Mitchell, E., Zhou, A., Sharma, A., Rafailov, R., Yao, H., Finn, C., Manning, C. D. (2023). *Just Ask for Calibration.* EMNLP 2023. [arXiv:2305.14975](https://arxiv.org/abs/2305.14975)
- Turpin, M., Michael, J., Perez, E., Bowman, S. R. (2023). *Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting.* [arXiv:2305.04388](https://arxiv.org/abs/2305.04388)
- Zhou, J., Lu, T., Mishra, S., Brahma, S., Basu, S., Luan, Y., Zhou, D., Hou, L. (2023). *Instruction-Following Evaluation for Large Language Models.* [arXiv:2311.07911](https://arxiv.org/abs/2311.07911)
