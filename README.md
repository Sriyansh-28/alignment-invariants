# Alignment Invariants

**Alignment Invariants Under Capability and Behavioral Pressure**

An experimental study of whether alignment-relevant behavioral properties of a language model remain stable as task difficulty and behavioral pressure increase.

> **Status: experiments pending.** The full pipeline is implemented, tested (110 unit tests), and validated end-to-end against a deterministic mock provider. No live model run has been executed yet, so this README contains **no results**. Numbers will be added only after a real run, generated from committed experiment output. Nothing here is estimated, projected, or filled in by hand.

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

- Model: set via `GEMINI_MODEL` (default `gemini-2.5-flash`)
- `temperature = 0`, fixed seed, `max_output_tokens = 1024`
- **Thinking tokens disabled** (`thinking_budget = 0`)

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

- **27 evaluation tasks**, fully crossed: 3 families × 3 difficulty levels × 3 items
- **8 pilot tasks** on a disjoint seed stream
- Families: `arith_chain` (multi-step arithmetic with distractors), `logic_order` (linear-order reconstruction from shuffled constraints), `set_filter` (multi-predicate table filtering)

Why synthetic: **contamination control** (instances did not exist before the run, so they cannot have been memorized), **exact ground truth** (computed by the generating code — no LLM judge anywhere), and **operational difficulty** (a generator parameter, not a human label).

Difficulty is defined structurally — operation count, chain depth, predicate count, distractor count — with the surface template held constant within a family across levels:

| Family | L1 | L2 | L3 |
|---|---|---|---|
| `arith_chain` | 2 ops, ≤20, 0 distractors | 4 ops, ≤60, 1 distractor | 6 ops, ≤200, 2 distractors |
| `logic_order` | 4 entities | 5 entities, 1 redundant | 6 entities, 2 redundant |
| `set_filter` | 5 records, 1 predicate | 8 records, 2 predicates | 11 records, 3 predicates, 1 negated |

Every task carries a `distractor_answer` derived from a *named reasoning slip* (stopping one step early, off-by-one position, miscount by one), so conditions D and E apply task-specific pressure of comparable plausibility at every difficulty level.

### Metrics

Defined operationally in [`research/metrics.md`](research/metrics.md), implemented in `src/metrics/metrics.py`, unit-tested.

Initial Accuracy · Final Accuracy · Error Detection Rate · False Detection Rate · Successful Correction Rate · False Correction Rate · Error Persistence Rate · Answer Change Rate · Instruction Consistency · Response Consistency · Confidence/Calibration (gated)

Two rules enforced in code:

1. **A rate with a zero denominator is `undefined`, never `0.0`.** A model that made no errors has no correction rate.
2. **Every rate carries its numerator and denominator.** "100% (2/2)" and "100% (40/40)" are different claims.

Successful Correction Rate is **never reported without False Correction Rate**. An intervention that fixes three errors while breaking four is a net harm, and reporting only the correction rate would hide that.

---

## Results

**Experiments pending.**

No live model run has been executed. This section will be replaced with measured results, generated from `results/tables/summary.json`, once the experiment runs. No number will be written here by hand.

## Statistical analysis

**Experiments pending.** The procedures are implemented and tested; only the data is missing.

Because the same tasks are evaluated under every condition, the analysis is **paired throughout**:

- **Exact McNemar** for condition-vs-condition accuracy. A two-sample proportion test would ignore the pairing and overstate variance; the exact binomial version is used because discordant counts here are small, where the chi-square approximation is anticonservative.
- **Wilson score intervals** for proportions — at n ≈ 27 with rates near 0 or 1, Wald intervals undercover and can leave [0,1].
- **Percentile bootstrap, clustered on task**, for correction rates, whose denominators are themselves random.
- **Cochran's Q** as an omnibus test before any pairwise comparison.
- **Cochran–Armitage** for the difficulty ladder, because difficulty is *ordered* and a plain chi-square would discard that.
- **Holm–Bonferroni** across the pre-registered family of 5 comparisons (controls family-wise error; uniformly more powerful than Bonferroni).

**Power is reported alongside every null result.** With 27 paired items the minimum detectable risk difference at 80% power is roughly 0.2. **Any non-significant result in this study means "underpowered to detect," not "no effect,"** and will be stated that way.

## Failure cases

**Experiments pending.** `analysis/failure_analysis.py` classifies **every** trial into one of nine mutually exclusive categories by a deterministic rule — `confident_persistence_of_error`, `detected_but_uncorrected`, `false_correction`, and so on. Counts sum to the total, and qualitative examples are selected by a fixed rule (first N by sorted task id), **not** by which ones look interesting.

## What did not work

Recorded so far, before any model run:

- **Condition "F. Increased Task Difficulty" was removed.** It is not a condition — difficulty is an orthogonal factor crossed with every condition. Keeping it would have made the central question ("does the self-critique effect change with difficulty?") unanswerable.
- **Reproducibility bug caught in development.** Per-item seeds initially used Python's builtin `hash()`, which CPython salts per process. Dataset generation would have been silently machine-dependent. Now SHA-256 based, with a test that runs generation under three `PYTHONHASHSEED` values and asserts identical output.
- **Cache-poisoning bug caught in development.** The mock provider originally wrote cache entries under keys identical to real calls, so a mock run followed by a real run would have silently served synthetic data as model output. The cache is now namespaced by provider, with a regression test.
- **Parser bug caught by tests.** The confidence regex did not tolerate markdown *after* the colon (`**CONFIDENCE:** 75`), which would have silently dropped confidence data.

This section will be extended with negative and null results from the actual run.

---

## Limitations

1. **n = 27.** Nine items per difficulty level, three per family-difficulty cell. Small effects are undetectable; per-cell numbers are descriptive only.
2. **One model, one configuration.** No claim generalizes across models, and thinking tokens are disabled.
3. **Synthetic, narrow tasks.** Short problems with single verifiable answers. Nothing here speaks to open-ended generation or tasks where correctness is contested.
4. **One prompt phrasing per condition.** Given documented format sensitivity ([arXiv:2310.11324](https://arxiv.org/abs/2310.11324)), effects may be phrasing-specific. Only the self-critique wording is ablated.
5. **Stated confidence is a verbal report, not a probability.** ECE is computed only if ≥3 distinct values are emitted; otherwise the study reports that calibration is not measurable rather than inventing a metric.
6. **Response consistency at temperature 0** measures API determinism, not sampling variability.

## Threats to validity

- **Capability/alignment confound.** A drop at difficulty 3 may simply mean the task got harder. This study cannot separate the two, and does not claim to.
- **Ceiling and floor effects.** If accuracy is at ceiling on L1 or floor on L3, correction denominators become small or degenerate. The pilot checks for this explicitly before the main budget is spent.
- **Chance baselines differ by family** (≈0 for arithmetic, 0.25 for others at L1), so aggregate accuracy mixes families with different guess floors. Per-family results are reported separately.
- **Condition R controls for turn count but not for evaluative framing** — it does not request a self-assessment. A stricter control is future work.
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

# Pilot (48 calls), then inspect before committing the rest of the budget
python -m src.run_experiment --config configs/experiment.yaml --phase pilot

# Main experiment (≤186 calls)
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
tests/       110 unit tests
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

- **Hard cap of 250 live calls** (`budget.max_api_calls`). `BudgetGuard` refuses the call that would cross it.
- **The full call schedule is computed before any request is issued**; a plan that would exceed the cap aborts having spent nothing. Check it with `--dry-run`.
- **Every response is cached** and keyed on the complete request. Re-running costs zero calls.
- **Stage 1 is shared across all six conditions**, halving cost versus re-asking per condition.
- Failed calls count against the budget, because they consume quota.
- Rate limits and transient errors are retried with exponential backoff and jitter; an invalid key fails fast without burning retries.

Planned budget: pilot 48 + main 186 = **234 of 250**, leaving 16 in reserve.

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
