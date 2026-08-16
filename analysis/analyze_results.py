"""Turn a results file into tables, figures, and a machine-readable summary.

    python -m analysis.analyze_results --results experiments/main_results.json

Everything the report and the dashboard display is produced here, so that no
number is ever typed by hand. The summary JSON written to
``results/tables/summary.json`` is the single source of truth for both.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Sequence

from analysis.statistical_tests import (bootstrap_paired_diff, bootstrap_rate_ci,
                                        cochran_armitage_trend, cochran_q,
                                        holm_bonferroni, mcnemar_exact,
                                        mde_paired, wilson_interval)
from src.metrics.metrics import (TrialRecord, compute_all, confidence_summary,
                                 expected_calibration_error,
                                 response_consistency, successful_correction_rate,
                                 false_correction_rate, initial_accuracy)

# Display order and short labels used in every table and figure.
CONDITION_LABELS = {
    "baseline": "A. Baseline",
    "reprompt_control": "R. Reprompt control",
    "self_critique": "B. Self-critique",
    "verification": "C. Verification",
    "conflicting_evidence": "D. Conflicting evidence",
    "preserve_pressure": "E. Preserve pressure",
}

# The pre-registered primary comparison family (see research/hypotheses.md).
PRIMARY_COMPARISONS = [
    ("baseline", "reprompt_control"),
    ("baseline", "self_critique"),
    ("reprompt_control", "self_critique"),
    ("baseline", "conflicting_evidence"),
    ("baseline", "preserve_pressure"),
]


def load_records(path: str | Path) -> tuple[list[TrialRecord], dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    records = [TrialRecord(**t) for t in payload["trials"]]
    return records, payload


def by_condition(records: Sequence[TrialRecord]) -> dict[str, list[TrialRecord]]:
    out: dict[str, list[TrialRecord]] = {}
    for r in records:
        out.setdefault(r.condition, []).append(r)
    return out


def paired_vectors(records: Sequence[TrialRecord], cond_a: str, cond_b: str
                   ) -> tuple[list[bool], list[bool], list[str]]:
    """Aligned correctness vectors over tasks present and parseable in BOTH
    conditions. Pairing is what licenses McNemar, so an item missing from
    either condition is dropped from both."""
    a = {r.task_id: r for r in records if r.condition == cond_a}
    b = {r.task_id: r for r in records if r.condition == cond_b}
    ids = sorted(set(a) & set(b))
    va, vb, kept = [], [], []
    for tid in ids:
        ca, cb = a[tid].final_correct, b[tid].final_correct
        if ca is None or cb is None:
            continue
        va.append(bool(ca))
        vb.append(bool(cb))
        kept.append(tid)
    return va, vb, kept


def analyze(records: list[TrialRecord], payload: dict[str, Any],
            cfg: dict[str, Any]) -> dict[str, Any]:
    conf_level = cfg.get("analysis", {}).get("confidence_level", 0.95)
    n_boot = cfg.get("analysis", {}).get("bootstrap_iterations", 10000)

    groups = by_condition(records)
    present = [c for c in CONDITION_LABELS if c in groups]

    summary: dict[str, Any] = {
        "meta": payload.get("meta", {}),
        "n_trials": len(records),
        "conditions": {},
        "by_difficulty": {},
        "by_family": {},
        "tests": {},
        "confidence": {},
        "probes": {},
        "data_quality": {},
    }

    # ---- data quality first: unparseable responses are reported, not hidden --
    unparsed = [r for r in records if not r.final_parsed]
    summary["data_quality"] = {
        "total_trials": len(records),
        "unparseable_final": len(unparsed),
        "unparseable_by_condition": {
            c: sum(1 for r in groups.get(c, []) if not r.final_parsed) for c in present},
        "stage1_unparseable_tasks": sorted({r.task_id for r in records
                                            if not r.initial_parsed}),
        "note": ("Unparseable responses are excluded from accuracy denominators "
                 "and are never counted as wrong answers."),
    }

    # ---- per-condition metrics with intervals ------------------------------
    for cond in present:
        recs = groups[cond]
        m = compute_all(recs)
        fa = m["final_accuracy"]
        ci = wilson_interval(fa["numerator"], fa["denominator"], conf_level)

        scr_num = [bool(r.initial_correct is False and r.final_correct is True) for r in recs]
        scr_den = [bool(r.initial_correct is False and r.final_correct is not None) for r in recs]
        fcr_num = [bool(r.initial_correct is True and r.final_correct is False) for r in recs]
        fcr_den = [bool(r.initial_correct is True and r.final_correct is not None) for r in recs]

        summary["conditions"][cond] = {
            "label": CONDITION_LABELS[cond],
            "n": len(recs),
            "metrics": m,
            "final_accuracy_ci": ci.to_dict(),
            "successful_correction_ci": bootstrap_rate_ci(
                scr_num, scr_den, n_boot=n_boot, confidence=conf_level).to_dict(),
            "false_correction_ci": bootstrap_rate_ci(
                fcr_num, fcr_den, n_boot=n_boot, confidence=conf_level).to_dict(),
            "net_change": {
                "gained": sum(scr_num),
                "lost": sum(fcr_num),
                "net": sum(scr_num) - sum(fcr_num),
            },
        }

    # ---- omnibus test across conditions ------------------------------------
    common_ids = None
    for cond in present:
        ids = {r.task_id for r in groups[cond] if r.final_correct is not None}
        common_ids = ids if common_ids is None else (common_ids & ids)
    common_ids = sorted(common_ids or [])

    if len(present) >= 2 and common_ids:
        vectors = {}
        for cond in present:
            lookup = {r.task_id: r for r in groups[cond]}
            vectors[cond] = [bool(lookup[t].final_correct) for t in common_ids]
        summary["tests"]["omnibus_cochran_q"] = cochran_q(vectors).to_dict()
        summary["tests"]["omnibus_n_common_tasks"] = len(common_ids)

    # ---- pre-registered pairwise family ------------------------------------
    pairwise: dict[str, Any] = {}
    pvals: dict[str, float] = {}
    for ca, cb in PRIMARY_COMPARISONS:
        if ca not in groups or cb not in groups:
            continue
        va, vb, kept = paired_vectors(records, ca, cb)
        if not kept:
            continue
        name = f"{ca}_vs_{cb}"
        res = mcnemar_exact(va, vb, name=name)
        diff = bootstrap_paired_diff(va, vb, n_boot=n_boot, confidence=conf_level)
        pairwise[name] = {
            "comparison": f"{CONDITION_LABELS[ca]} vs {CONDITION_LABELS[cb]}",
            "test": res.to_dict(),
            "paired_difference_ci": diff.to_dict(),
            "n_pairs": len(kept),
        }
        if res.p_value is not None:
            pvals[name] = res.p_value

    adjusted = holm_bonferroni(pvals, alpha=1 - conf_level)
    for name, adj in adjusted.items():
        pairwise[name]["holm"] = adj
    summary["tests"]["primary_pairwise"] = pairwise
    summary["tests"]["multiplicity"] = {
        "method": "holm-bonferroni",
        "family_size": len(pvals),
        "family": list(pvals),
    }

    # ---- difficulty ladder --------------------------------------------------
    difficulties = sorted({r.difficulty for r in records})
    for cond in present:
        recs = groups[cond]
        per_diff = {}
        succ, tot = [], []
        for d in difficulties:
            sub = [r for r in recs if r.difficulty == d]
            m = compute_all(sub)
            fa = m["final_accuracy"]
            per_diff[str(d)] = {
                "metrics": m,
                "accuracy_ci": wilson_interval(fa["numerator"], fa["denominator"],
                                               conf_level).to_dict(),
                "n": len(sub),
            }
            succ.append(fa["numerator"])
            tot.append(fa["denominator"])
        trend = cochran_armitage_trend(succ, tot)
        summary["by_difficulty"][cond] = {
            "label": CONDITION_LABELS[cond],
            "levels": per_diff,
            "trend_test": trend.to_dict(),
        }

    # ---- correction efficacy across difficulty (H7) -------------------------
    scr_by_diff = {}
    for d in difficulties:
        sub = [r for r in records
               if r.difficulty == d and r.condition in ("self_critique", "verification")]
        scr = successful_correction_rate(sub)
        fcr = false_correction_rate(sub)
        scr_by_diff[str(d)] = {"successful_correction": scr.to_dict(),
                               "false_correction": fcr.to_dict()}
    summary["by_difficulty"]["_correction_efficacy_B_and_C"] = scr_by_diff

    # ---- per-family breakdown ----------------------------------------------
    for fam in sorted({r.family for r in records}):
        summary["by_family"][fam] = {}
        for cond in present:
            sub = [r for r in groups[cond] if r.family == fam]
            summary["by_family"][fam][cond] = compute_all(sub)

    # ---- confidence ---------------------------------------------------------
    for cond in present:
        cs = confidence_summary(groups[cond], which="final")
        cs["ece"] = expected_calibration_error(groups[cond], which="final")
        summary["confidence"][cond] = cs

    # ---- probes -------------------------------------------------------------
    probes = payload.get("probes", {})
    if "consistency" in probes:
        pairs = [(p["rep0"], p["rep1"]) for p in probes["consistency"]]
        rc = response_consistency(pairs)
        summary["probes"]["response_consistency"] = {
            **rc.to_dict(),
            "disagreements": [p for p in probes["consistency"] if p.get("agree") is False],
            "note": ("Measured at temperature 0 with a fixed seed, so this "
                     "reflects API determinism, not sampling variability."),
        }
    if "prompt_ablation" in probes:
        rows = probes["prompt_ablation"]["rows"]
        n_i = sum(1 for r in rows if r["initial_correct"])
        n_f = sum(1 for r in rows if r["final_correct"])
        summary["probes"]["prompt_ablation"] = {
            "name": probes["prompt_ablation"]["name"],
            "n": len(rows),
            "initial_correct": n_i,
            "final_correct": n_f,
            "changed": sum(1 for r in rows
                           if r["initial_answer"] != r["final_answer"]),
        }
        # Compare against condition B on the same task subset.
        ids = [r["task_id"] for r in rows]
        b = {r.task_id: r for r in groups.get("self_critique", [])}
        va = [bool(b[t].final_correct) for t in ids
              if t in b and b[t].final_correct is not None]
        vb = [bool(r["final_correct"]) for r in rows
              if r["task_id"] in b and b[r["task_id"]].final_correct is not None]
        if va and len(va) == len(vb):
            summary["probes"]["prompt_ablation"]["vs_condition_B"] = \
                mcnemar_exact(va, vb, name="B_vs_Balt").to_dict()

    # ---- power --------------------------------------------------------------
    n_pairs = len(common_ids)
    summary["power"] = mde_paired(n_pairs)
    summary["power"]["interpretation"] = (
        f"With {n_pairs} paired items, differences in accuracy smaller than "
        f"~{summary['power']['mde_risk_difference']:.2f} are not reliably "
        f"detectable. Non-significant results below should be read as "
        f"'underpowered to detect', not as evidence of no effect."
    ) if summary["power"].get("mde_risk_difference") else ""

    return summary


def write_tables(summary: dict[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    # main per-condition table
    p = out_dir / "condition_metrics.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["condition", "label", "n", "final_accuracy", "acc_lo", "acc_hi",
                    "initial_accuracy", "successful_correction", "scr_n", "scr_d",
                    "false_correction", "fcr_n", "fcr_d", "error_persistence",
                    "answer_change_rate", "error_detection", "false_detection",
                    "instruction_consistency", "gained", "lost", "net"])
        for cond, c in summary["conditions"].items():
            m = c["metrics"]
            ci = c["final_accuracy_ci"]
            w.writerow([
                cond, c["label"], c["n"],
                _f(m["final_accuracy"]["value"]), _f(ci["low"]), _f(ci["high"]),
                _f(m["initial_accuracy"]["value"]),
                _f(m["successful_correction_rate"]["value"]),
                m["successful_correction_rate"]["numerator"],
                m["successful_correction_rate"]["denominator"],
                _f(m["false_correction_rate"]["value"]),
                m["false_correction_rate"]["numerator"],
                m["false_correction_rate"]["denominator"],
                _f(m["error_persistence_rate"]["value"]),
                _f(m["answer_change_rate"]["value"]),
                _f(m["error_detection_rate"]["value"]),
                _f(m["false_detection_rate"]["value"]),
                _f(m["instruction_consistency"]["value"]),
                c["net_change"]["gained"], c["net_change"]["lost"], c["net_change"]["net"],
            ])
    written.append(p)

    # difficulty table
    p = out_dir / "difficulty_metrics.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["condition", "difficulty", "n", "final_accuracy",
                    "acc_lo", "acc_hi", "instruction_consistency"])
        for cond, blk in summary["by_difficulty"].items():
            if cond.startswith("_"):
                continue
            for d, lv in blk["levels"].items():
                w.writerow([cond, d, lv["n"],
                            _f(lv["metrics"]["final_accuracy"]["value"]),
                            _f(lv["accuracy_ci"]["low"]), _f(lv["accuracy_ci"]["high"]),
                            _f(lv["metrics"]["instruction_consistency"]["value"])])
    written.append(p)

    # statistical tests table
    p = out_dir / "statistical_tests.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["comparison", "n_pairs", "acc_a", "acc_b", "b01_a_right_b_wrong",
                    "b10_a_wrong_b_right", "risk_difference", "diff_ci_lo",
                    "diff_ci_hi", "p_raw", "p_holm_adjusted", "reject_at_0.05"])
        for name, blk in summary["tests"].get("primary_pairwise", {}).items():
            t, e = blk["test"], blk["test"]["effect"]
            holm = blk.get("holm", {})
            d = blk["paired_difference_ci"]
            w.writerow([blk["comparison"], blk["n_pairs"],
                        _f(e.get("acc_a")), _f(e.get("acc_b")),
                        e.get("b01"), e.get("b10"), _f(e.get("risk_difference")),
                        _f(d.get("low")), _f(d.get("high")),
                        _f(t.get("p_value"), 4), _f(holm.get("p_adjusted"), 4),
                        holm.get("reject_at_alpha")])
    written.append(p)

    p = out_dir / "summary.json"
    p.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    written.append(p)
    return written


def _f(v: Any, nd: int = 3) -> str:
    if v is None:
        return "undefined"
    if isinstance(v, bool):
        return str(v)
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def write_figures(summary: dict[str, Any], out_dir: Path) -> list[Path]:
    """Static charts with error bars. No styling flourishes; these are figures
    for a report, and every one is generated from summary.json."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    conds = list(summary["conditions"])
    if not conds:
        return written

    # Figure 1: accuracy by condition with Wilson intervals
    labels = [summary["conditions"][c]["label"] for c in conds]
    vals, los, his = [], [], []
    for c in conds:
        ci = summary["conditions"][c]["final_accuracy_ci"]
        v = ci["point"] or 0.0
        vals.append(v)
        los.append(v - (ci["low"] or v))
        his.append((ci["high"] or v) - v)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(range(len(conds)), vals, yerr=[los, his], capsize=4,
           color="#4C72B0", edgecolor="black", linewidth=0.6)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Final accuracy")
    ax.set_ylim(0, 1)
    ax.set_title("Accuracy by condition (95% Wilson intervals)", fontsize=10)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)
    fig.tight_layout()
    p = out_dir / "accuracy_by_condition.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written.append(p)

    # Figure 2: accuracy across the difficulty ladder, one line per condition
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for c in conds:
        blk = summary["by_difficulty"].get(c)
        if not blk:
            continue
        xs = sorted(blk["levels"], key=int)
        ys = [blk["levels"][d]["metrics"]["final_accuracy"]["value"] for d in xs]
        xs_p = [int(x) for x, y in zip(xs, ys) if y is not None]
        ys_p = [y for y in ys if y is not None]
        if xs_p:
            ax.plot(xs_p, ys_p, marker="o", label=summary["conditions"][c]["label"],
                    linewidth=1.3, markersize=4)
    ax.set_xlabel("Difficulty level")
    ax.set_ylabel("Final accuracy")
    ax.set_xticks([1, 2, 3])
    ax.set_ylim(0, 1)
    ax.set_title("Accuracy across the difficulty ladder", fontsize=10)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, linewidth=0.5)
    fig.tight_layout()
    p = out_dir / "accuracy_by_difficulty.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written.append(p)

    # Figure 3: gains vs losses per condition (the net-effect accounting)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    gains = [summary["conditions"][c]["net_change"]["gained"] for c in conds]
    losses = [-summary["conditions"][c]["net_change"]["lost"] for c in conds]
    ax.bar(range(len(conds)), gains, color="#55A868", edgecolor="black",
           linewidth=0.6, label="errors fixed")
    ax.bar(range(len(conds)), losses, color="#C44E52", edgecolor="black",
           linewidth=0.6, label="correct answers broken")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Number of tasks")
    ax.set_title("Errors fixed vs correct answers broken", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)
    fig.tight_layout()
    p = out_dir / "correction_tradeoff.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written.append(p)

    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analyze experiment results.")
    ap.add_argument("--results", default="experiments/main_results.json")
    ap.add_argument("--config", default="configs/experiment.yaml")
    ap.add_argument("--tables", default="results/tables")
    ap.add_argument("--figures", default="results/figures")
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)

    if not Path(args.results).exists():
        print(f"ERROR: {args.results} not found. Run the experiment first.")
        return 1

    import yaml
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    records, payload = load_records(args.results)
    if not records:
        print("ERROR: results file contains no trials.")
        return 1

    summary = analyze(records, payload, cfg)
    written = write_tables(summary, Path(args.tables))
    if not args.no_figures:
        written += write_figures(summary, Path(args.figures))

    meta = summary["meta"]
    if not meta.get("is_real_model_output", False):
        print("\n*** WARNING: this results file is MOCK output, not model output. ***")

    print(f"\nconditions analyzed : {len(summary['conditions'])}")
    print(f"trials              : {summary['n_trials']}")
    print(f"unparseable finals  : {summary['data_quality']['unparseable_final']}")
    for p in written:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
