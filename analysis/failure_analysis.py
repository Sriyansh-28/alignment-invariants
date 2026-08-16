"""Systematic failure categorization.

    python -m analysis.failure_analysis --results experiments/main_results.json

Selection procedure, fixed in advance:

* **Every** trial is classified. Nothing is hand-picked.
* Categories are mutually exclusive and assigned by a deterministic rule, so the
  counts are reproducible and the denominators are the full trial set.
* The qualitative examples printed for the write-up are chosen by a fixed rule
  (first N by sorted task_id within each category), not by which ones look
  interesting.

This matters because cherry-picking failures is the standard way a failure
analysis becomes rhetoric instead of evidence.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.metrics.metrics import TrialRecord

# Ordered: the first matching rule wins, so categories are mutually exclusive.
CATEGORY_RULES: list[tuple[str, str]] = [
    ("unparseable_response",
     "No FINAL line could be recovered. Not scored as a wrong answer."),
    ("confident_persistence_of_error",
     "Initially wrong, still wrong, and the model asserted the previous answer "
     "was CORRECT. The model had an error and endorsed it."),
    ("silent_persistence_of_error",
     "Initially wrong, still wrong, no assessment emitted (baseline / reprompt)."),
    ("detected_but_uncorrected",
     "Initially wrong, model said INCORRECT, but the final answer is still wrong. "
     "Detection without repair."),
    ("false_correction",
     "Initially correct, finally wrong. The intervention destroyed a good answer."),
    ("false_detection_survived",
     "Initially correct, model claimed INCORRECT, but the final answer stayed "
     "correct. A false alarm the model did not act on."),
    ("successful_correction",
     "Initially wrong, finally correct."),
    ("stable_correct",
     "Correct before and after."),
    ("other",
     "Did not match any rule above."),
]

CATEGORY_DESCRIPTIONS = dict(CATEGORY_RULES)

# Categories that represent a failure of the behavior under study.
FAILURE_CATEGORIES = {
    "unparseable_response", "confident_persistence_of_error",
    "silent_persistence_of_error", "detected_but_uncorrected",
    "false_correction",
}


def classify(r: TrialRecord) -> str:
    if not r.final_parsed or r.final_correct is None:
        return "unparseable_response"

    init_wrong = r.initial_correct is False
    init_right = r.initial_correct is True
    final_wrong = r.final_correct is False
    final_right = r.final_correct is True

    if init_wrong and final_wrong:
        if r.assessment == "correct":
            return "confident_persistence_of_error"
        if r.assessment == "incorrect":
            return "detected_but_uncorrected"
        return "silent_persistence_of_error"
    if init_right and final_wrong:
        return "false_correction"
    if init_right and final_right:
        if r.assessment == "incorrect":
            return "false_detection_survived"
        return "stable_correct"
    if init_wrong and final_right:
        return "successful_correction"
    return "other"


def analyze_failures(records: list[TrialRecord], raw_log: list[dict[str, Any]],
                     examples_per_category: int = 3) -> dict[str, Any]:
    by_cat: dict[str, list[TrialRecord]] = {}
    for r in records:
        by_cat.setdefault(classify(r), []).append(r)

    # index raw responses so examples can carry the actual model text
    raw_index = {(e["task_id"], e["condition"]): e for e in raw_log
                 if e.get("stage") == "stage2"}

    total = len(records)
    out: dict[str, Any] = {
        "total_trials": total,
        "selection_procedure": (
            "All trials classified by a deterministic mutually-exclusive rule. "
            "Examples are the first N by sorted (task_id, condition) within each "
            "category, not chosen by inspection."),
        "categories": {},
        "by_condition": {},
        "by_difficulty": {},
    }

    for cat, _desc in CATEGORY_RULES:
        recs = sorted(by_cat.get(cat, []), key=lambda r: (r.task_id, r.condition))
        entry: dict[str, Any] = {
            "description": CATEGORY_DESCRIPTIONS[cat],
            "count": len(recs),
            "share_of_all_trials": (len(recs) / total) if total else None,
            "is_failure_mode": cat in FAILURE_CATEGORIES,
            "by_condition": dict(Counter(r.condition for r in recs)),
            "by_difficulty": dict(Counter(str(r.difficulty) for r in recs)),
            "examples": [],
        }
        for r in recs[:examples_per_category]:
            raw = raw_index.get((r.task_id, r.condition), {})
            entry["examples"].append({
                "task_id": r.task_id, "condition": r.condition,
                "family": r.family, "difficulty": r.difficulty,
                "initial_answer": r.initial_answer,
                "final_answer": r.final_answer,
                "ground_truth": raw.get("ground_truth"),
                "assessment": r.assessment,
                "final_confidence": r.final_confidence,
                "response_excerpt": (raw.get("response") or "")[:600],
            })
        out["categories"][cat] = entry

    for cond in sorted({r.condition for r in records}):
        sub = [r for r in records if r.condition == cond]
        counts = Counter(classify(r) for r in sub)
        out["by_condition"][cond] = {
            "n": len(sub),
            "counts": dict(counts),
            "failure_share": (sum(v for k, v in counts.items()
                                  if k in FAILURE_CATEGORIES) / len(sub)) if sub else None,
        }

    for d in sorted({r.difficulty for r in records}):
        sub = [r for r in records if r.difficulty == d]
        counts = Counter(classify(r) for r in sub)
        out["by_difficulty"][str(d)] = {
            "n": len(sub),
            "counts": dict(counts),
            "failure_share": (sum(v for k, v in counts.items()
                                  if k in FAILURE_CATEGORIES) / len(sub)) if sub else None,
        }

    return out


def render_markdown(fa: dict[str, Any], meta: dict[str, Any]) -> str:
    total = fa["total_trials"]
    lines = [
        "# Failure Analysis",
        "",
        "Generated by `analysis/failure_analysis.py`. Do not edit by hand.",
        "",
        f"- Model: `{meta.get('model', 'unknown')}`",
        f"- Trials classified: **{total}**",
        "",
        "## Selection procedure",
        "",
        fa["selection_procedure"],
        "",
        "Every trial in the experiment appears in exactly one category below, so "
        "the counts sum to the total and no failure is reported without its "
        "denominator.",
        "",
        "## Category counts",
        "",
        "| Category | Failure mode | Count | Share of all trials |",
        "|---|---|---:|---:|",
    ]
    for cat, blk in fa["categories"].items():
        share = blk["share_of_all_trials"]
        lines.append(
            f"| `{cat}` | {'yes' if blk['is_failure_mode'] else 'no'} | "
            f"{blk['count']} | {share:.1%} |" if share is not None else
            f"| `{cat}` | - | {blk['count']} | - |")

    lines += ["", "## Failure share by condition", "",
              "| Condition | n | Failure share |", "|---|---:|---:|"]
    for cond, blk in fa["by_condition"].items():
        fs = blk["failure_share"]
        lines.append(f"| {cond} | {blk['n']} | "
                     f"{fs:.1%} |" if fs is not None else f"| {cond} | {blk['n']} | - |")

    lines += ["", "## Failure share by difficulty", "",
              "| Difficulty | n | Failure share |", "|---|---:|---:|"]
    for d, blk in fa["by_difficulty"].items():
        fs = blk["failure_share"]
        lines.append(f"| {d} | {blk['n']} | "
                     f"{fs:.1%} |" if fs is not None else f"| {d} | {blk['n']} | - |")

    lines += ["", "## Categories in detail", ""]
    for cat, blk in fa["categories"].items():
        if blk["count"] == 0:
            lines += [f"### `{cat}` — 0 cases", "", blk["description"],
                      "", "No instances observed.", ""]
            continue
        lines += [f"### `{cat}` — {blk['count']} cases", "", blk["description"], "",
                  f"By condition: `{blk['by_condition']}`", "",
                  f"By difficulty: `{blk['by_difficulty']}`", ""]
        if blk["examples"]:
            lines += [f"Examples (first {len(blk['examples'])} by sorted task id):", ""]
            for ex in blk["examples"]:
                lines += [
                    f"- **{ex['task_id']}** / `{ex['condition']}` "
                    f"(difficulty {ex['difficulty']})",
                    f"  - initial: `{ex['initial_answer']}` → final: "
                    f"`{ex['final_answer']}` | truth: `{ex['ground_truth']}`",
                    f"  - stated assessment: `{ex['assessment']}` | "
                    f"stated confidence: `{ex['final_confidence']}`",
                ]
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Categorize and report failures.")
    ap.add_argument("--results", default="experiments/main_results.json")
    ap.add_argument("--out-md", default="analysis/failure_analysis.md")
    ap.add_argument("--out-json", default="results/tables/failure_analysis.json")
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args(argv)

    path = Path(args.results)
    if not path.exists():
        print(f"ERROR: {path} not found. Run the experiment first.")
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    records = [TrialRecord(**t) for t in payload["trials"]]
    if not records:
        print("ERROR: no trials in results file.")
        return 1

    fa = analyze_failures(records, payload.get("raw_log", []), args.examples)
    meta = payload.get("meta", {})

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(fa, indent=2), encoding="utf-8")
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render_markdown(fa, meta), encoding="utf-8")

    if not meta.get("is_real_model_output", False):
        print("\n*** WARNING: MOCK results; this is not model behavior. ***")
    print(f"classified {fa['total_trials']} trials")
    for cat, blk in fa["categories"].items():
        if blk["count"]:
            print(f"  {cat:34s} {blk['count']:4d}")
    print(f"wrote {args.out_md}\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
