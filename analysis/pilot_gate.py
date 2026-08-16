"""Pilot validation gate.

    python -m analysis.pilot_gate --results experiments/pilot_results.json

The pilot exists to catch design defects *before* the remaining API budget is
spent. This script makes that check mechanical rather than a matter of eyeballing
the output, and it exits non-zero if any gate fails, so it can be wired into a
run script.

The five gates correspond one-to-one with the pre-run checklist:

  1. tasks have valid ground truth
  2. metrics are computable
  3. conditions are meaningfully different
  4. no obvious confound invalidates the experiment
  5. the API response format is stable

A failed gate is not a reason to tweak numbers until it passes. It is a reason
to fix the design and re-pilot, recording the change in research/hypotheses.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.evaluation.extract import parse_response
from src.metrics.metrics import (TrialRecord, compute_all, initial_accuracy,
                                 instruction_consistency)
from src.tasks.generators import Task, normalize_answer

# A pilot this small cannot support a real power calculation; these thresholds
# are deliberately loose and are about detecting *broken design*, not effects.
MIN_FORMAT_COMPLIANCE = 0.80
MIN_PARSE_RATE = 0.85
CEILING = 0.95
FLOOR = 0.05


class Gate:
    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self.passed: bool | None = None
        self.detail: list[str] = []
        self.blocking = True

    def check(self, ok: bool, msg: str) -> None:
        self.detail.append(("  ok   " if ok else "  FAIL ") + msg)
        self.passed = ok if self.passed is None else (self.passed and ok)

    def note(self, msg: str) -> None:
        self.detail.append("  note " + msg)


def gate_ground_truth(tasks: list[Task]) -> Gate:
    g = Gate("ground_truth", "Tasks have valid, well-formed ground truth")
    if not tasks:
        g.check(False, "no tasks in results file")
        return g
    g.check(all(t.answer and t.answer.strip() for t in tasks),
            f"all {len(tasks)} tasks have a non-empty answer")
    g.check(all(t.answer == normalize_answer(t.answer) for t in tasks),
            "all ground-truth answers are already in normalized form")
    bad = [t.task_id for t in tasks if t.distractor_answer == t.answer]
    g.check(not bad,
            "distractor answers differ from ground truth"
            + (f" (violations: {bad})" if bad else ""))
    ints = [t for t in tasks if t.answer_type == "integer"]
    g.check(all(t.answer.lstrip("-").isdigit() for t in ints),
            f"all {len(ints)} integer answers parse as integers")
    return g


def gate_metrics_computable(records: list[TrialRecord]) -> Gate:
    g = Gate("metrics_computable", "Metrics have usable denominators")
    by_cond: dict[str, list[TrialRecord]] = {}
    for r in records:
        by_cond.setdefault(r.condition, []).append(r)

    ia = initial_accuracy(records)
    g.check(ia.value is not None, f"initial accuracy is defined ({ia})")

    # The correction metrics are the point of the study. If the model makes no
    # errors on the pilot, their denominators are empty and the main run would
    # produce undefined correction rates.
    n_errors = sum(1 for r in records
                   if r.condition == "baseline" and r.initial_correct is False)
    g.check(n_errors > 0,
            f"baseline produced {n_errors} initial error(s); correction metrics "
            f"need a non-empty error denominator")
    if 0 < n_errors < 3:
        g.note(f"only {n_errors} initial error(s) in the pilot - correction rates "
               f"in the main run may rest on very small denominators")

    for cond in ("self_critique", "verification"):
        sub = by_cond.get(cond, [])
        if not sub:
            continue
        with_assessment = sum(1 for r in sub if r.assessment is not None)
        g.check(with_assessment > 0,
                f"{cond}: {with_assessment}/{len(sub)} trials emitted an "
                f"ASSESSMENT (needed for error-detection rate)")
    return g


def gate_conditions_differ(records: list[TrialRecord]) -> Gate:
    g = Gate("conditions_differ", "Conditions produce meaningfully different behavior")
    by_cond: dict[str, list[TrialRecord]] = {}
    for r in records:
        by_cond.setdefault(r.condition, []).append(r)

    changed = {}
    for cond, sub in sorted(by_cond.items()):
        if cond == "baseline":
            continue
        n = sum(1 for r in sub if r.changed_answer)
        d = sum(1 for r in sub if r.changed_answer is not None)
        changed[cond] = (n, d)
        g.note(f"{cond}: answer changed in {n}/{d} trials")

    any_movement = any(n > 0 for n, _ in changed.values())
    g.check(any_movement,
            "at least one intervention moved at least one answer; if nothing "
            "ever moves, the manipulations are inert")

    # A pilot cannot establish that conditions differ statistically. It can only
    # confirm they are not obviously identical.
    sigs = {c: tuple(sorted((r.task_id, r.final_answer) for r in sub))
            for c, sub in by_cond.items()}
    dupes = [(a, b) for i, a in enumerate(sigs) for b in list(sigs)[i + 1:]
             if sigs[a] == sigs[b]]
    if dupes:
        g.note(f"conditions with byte-identical answer sets: {dupes} - expected "
               f"for near-inert manipulations at this sample size, but worth "
               f"checking the prompts actually differ")
    return g


def gate_no_obvious_confound(records: list[TrialRecord], tasks: list[Task]) -> Gate:
    g = Gate("no_obvious_confound", "No ceiling/floor effect or broken difficulty ladder")
    base = [r for r in records if r.condition == "baseline"]
    if not base:
        g.check(False, "no baseline trials")
        return g

    acc = initial_accuracy(base)
    if acc.value is None:
        g.check(False, "baseline accuracy undefined")
        return g

    g.check(acc.value < CEILING,
            f"baseline accuracy {acc.value:.2f} is below the {CEILING} ceiling "
            f"(at ceiling there are no errors to correct)")
    g.check(acc.value > FLOOR,
            f"baseline accuracy {acc.value:.2f} is above the {FLOOR} floor "
            f"(at floor, correction is measuring noise)")

    by_diff: dict[int, list[TrialRecord]] = {}
    for r in base:
        by_diff.setdefault(r.difficulty, []).append(r)
    profile = {}
    for d in sorted(by_diff):
        a = initial_accuracy(by_diff[d])
        profile[d] = a.value
        g.note(f"difficulty {d}: accuracy {a}")

    vals = [v for v in profile.values() if v is not None]
    if len(vals) >= 2:
        monotone = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
        if monotone:
            g.check(True, "accuracy is non-increasing across difficulty "
                          "(manipulation check H6 looks intact)")
        else:
            # Not fatal at n=8, but it must be surfaced rather than ignored.
            g.check(True, f"accuracy is NOT monotone across difficulty ({profile}); "
                          f"at pilot n this is weak evidence, but if it persists in "
                          f"the main run the difficulty ladder did not work and "
                          f"difficulty-based claims are uninterpretable")
            g.note("treated as non-blocking at pilot sample size")

    fams = {t.family for t in tasks}
    diffs = {t.difficulty for t in tasks}
    g.note(f"pilot covers {len(fams)} families {sorted(fams)} and "
           f"{len(diffs)} difficulty levels {sorted(diffs)}")
    return g


def gate_response_format(records: list[TrialRecord], raw_log: list[dict[str, Any]]) -> Gate:
    g = Gate("response_format", "API response format is stable and parseable")
    if not records:
        g.check(False, "no trials")
        return g

    ic = instruction_consistency(records)
    g.check(ic.value is not None and ic.value >= MIN_FORMAT_COMPLIANCE,
            f"format compliance {ic} >= {MIN_FORMAT_COMPLIANCE}")

    parsed = sum(1 for r in records if r.final_parsed)
    rate = parsed / len(records)
    g.check(rate >= MIN_PARSE_RATE,
            f"parse rate {parsed}/{len(records)} = {rate:.2f} >= {MIN_PARSE_RATE}")

    failures = [e for e in raw_log if not e.get("ok")]
    g.check(not failures,
            f"{len(failures)} failed API call(s)"
            + (f": {[e.get('error') for e in failures][:5]}" if failures else ""))

    # Confidence is optional per-metric but a total absence means the calibration
    # analysis cannot run at all, which should be known before the main spend.
    confs = {r.final_confidence for r in records if r.final_confidence is not None}
    if len(confs) == 0:
        g.check(False, "no CONFIDENCE values parsed at all; calibration analysis "
                       "would be impossible")
    elif len(confs) < 3:
        g.note(f"stated confidence took only {len(confs)} distinct value(s) "
               f"({sorted(confs)}); per the pre-registered gate, ECE will NOT be "
               f"computed and this will be reported as a measurement limitation")
    else:
        g.note(f"stated confidence took {len(confs)} distinct values")

    unparsed = [e for e in raw_log
                if e.get("ok") and parse_response(e.get("response", "")).answer is None]
    if unparsed:
        g.note(f"{len(unparsed)} successful call(s) produced unparseable output; "
               f"first example task {unparsed[0].get('task_id')}")
    return g


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate pilot before main spend.")
    ap.add_argument("--results", default="experiments/pilot_results.json")
    ap.add_argument("--out-json", default="results/tables/pilot_gate.json")
    args = ap.parse_args(argv)

    path = Path(args.results)
    if not path.exists():
        print(f"ERROR: {path} not found. Run the pilot first:\n"
              f"  python -m src.run_experiment --config configs/experiment.yaml "
              f"--phase pilot")
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    records = [TrialRecord(**t) for t in payload["trials"]]
    tasks = [Task(**t) for t in payload.get("tasks", [])]
    raw_log = payload.get("raw_log", [])
    meta = payload.get("meta", {})

    if not meta.get("is_real_model_output", False):
        print("*** WARNING: this pilot file is MOCK output. Gates below validate "
              "the pipeline, not the model. ***\n")

    gates = [
        gate_ground_truth(tasks),
        gate_metrics_computable(records),
        gate_conditions_differ(records),
        gate_no_obvious_confound(records, tasks),
        gate_response_format(records, raw_log),
    ]

    print("=" * 72)
    print(f"PILOT GATE  —  {len(records)} trials, {len(tasks)} tasks, "
          f"model={meta.get('model', '?')}")
    b = meta.get("budget", {})
    if b:
        print(f"budget: {b.get('live_calls')} live / {b.get('max_calls')} cap, "
              f"{b.get('failed_calls')} failed, {b.get('cache_hits')} cached, "
              f"{b.get('total_tokens')} tokens")
    print("=" * 72)

    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        print(f"\n[{status}] {g.name} — {g.description}")
        for line in g.detail:
            print(line)

    overall = all(g.passed for g in gates)
    print("\n" + "=" * 72)
    if overall:
        print("ALL GATES PASSED — the design is validated; the main run may proceed.")
    else:
        print("GATE FAILURE — do NOT spend the remaining budget.")
        print("Fix the design, record the change in research/hypotheses.md, re-pilot.")
    print("=" * 72)

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps({
        "overall_pass": overall,
        "is_real_model_output": meta.get("is_real_model_output", False),
        "gates": [{"name": g.name, "description": g.description,
                   "passed": g.passed, "detail": g.detail} for g in gates],
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out_json}")
    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())
