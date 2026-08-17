"""Experiment runner.

    python -m src.run_experiment --config configs/experiment.yaml --phase pilot
    python -m src.run_experiment --config configs/experiment.yaml --phase main

Call-budget discipline:

* The full call schedule is computed before any request is issued. If the plan
  exceeds ``budget.max_api_calls`` the run aborts without spending anything.
* ``BudgetGuard`` independently refuses any call that would cross the cap, so a
  bug in the planner cannot overspend.
* Stage 1 is issued once per task and shared by all six conditions. This halves
  the cost relative to re-asking per condition and, more importantly, makes the
  conditions exactly paired: every intervention acts on the identical initial
  answer rather than on a fresh sample.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.caching.cache import ResponseCache
from src.caching.ledger import (DEFAULT_LEDGER, BudgetLedger,
                                LedgerExceededError)
from src.evaluation.extract import Parsed, is_correct, parse_response
from src.gemini.client import (APIKeyError, BudgetExceededError, BudgetGuard,
                               QuotaExhaustedError,
                               CachedModel, GeminiProvider, load_api_key)
from src.metrics.metrics import TrialRecord
from src.tasks.generators import Task, generate_dataset


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader so the project has no hard dependency on python-dotenv."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def select_pilot_tasks(cfg: dict[str, Any]) -> list[Task]:
    """Purposive pilot sample defined by ``dataset.pilot_cells``."""
    ds = cfg["dataset"]
    cells = [tuple(c) for c in ds["pilot_cells"]]
    all_pilot = generate_dataset(
        seed=cfg["seed"], n_per_cell=ds["pilot_n_per_cell"],
        families=tuple(ds["families"]), difficulties=tuple(ds["difficulties"]),
        split=ds["pilot_split"],
    )
    wanted = {(f, int(d)) for f, d in cells}
    return [t for t in all_pilot if (t.family, t.difficulty) in wanted]


def select_eval_tasks(cfg: dict[str, Any]) -> list[Task]:
    ds = cfg["dataset"]
    return generate_dataset(
        seed=cfg["seed"], n_per_cell=ds["n_per_cell"],
        families=tuple(ds["families"]), difficulties=tuple(ds["difficulties"]),
        split=ds["eval_split"],
    )


def plan_calls(cfg: dict[str, Any], n_tasks: int, phase: str) -> dict[str, int]:
    """Compute the live-call schedule before spending anything."""
    conditions = cfg["conditions"]
    n_two_turn = sum(1 for c in conditions if c != "baseline")
    plan = {"stage1": n_tasks, "stage2": n_tasks * n_two_turn}
    if phase == "main":
        probes = cfg.get("probes", {})
        if probes.get("consistency", {}).get("enabled"):
            p = probes["consistency"]
            plan["consistency_probe"] = min(p["n_tasks"], n_tasks) * p["repeats"]
        if probes.get("prompt_ablation", {}).get("enabled"):
            plan["prompt_ablation"] = min(probes["prompt_ablation"]["n_tasks"], n_tasks)
    plan["total"] = sum(v for k, v in plan.items() if k != "total")
    return plan


def plan_live_calls(cfg: dict[str, Any], prompts: dict[str, Any], phase: str,
                    model: CachedModel, tasks: list[Task]) -> dict[str, int]:
    """How many live calls this run would actually cost, given the cache.

    ``plan_calls`` gives the worst case, which is the right number to check
    before a first run and the wrong number to check before a resume: after a
    session that completed most of the experiment, the worst case still says
    "240 calls" even though 200 of them are already on disk and free. Reserving
    against that figure would refuse to resume a run that costs almost nothing.

    Stage-2 prompts embed the stage-1 answer, so a stage-2 key only exists once
    stage 1 is cached. Where stage 1 is still missing, its dependent stage-2
    calls are counted as needed -- which they are, and which keeps this an
    upper bound that converges to the exact figure as the run progresses.
    """
    mcfg = cfg["model"]
    common = dict(temperature=mcfg["temperature"],
                  max_output_tokens=mcfg["max_output_tokens"],
                  seed=mcfg.get("seed"), thinking_budget=mcfg.get("thinking_budget"))
    systems = prompts["system"]
    cond_specs = prompts["conditions"]

    needed = {"stage1": 0, "stage2": 0}
    # Three states, not two. "missing" means stage 1 has yet to be called, so
    # its dependent stage-2 calls are unknown and must be reserved for.
    # "unparseable" means stage 1 was called and returned nothing gradeable:
    # the runner records those trials as unusable without issuing a stage-2
    # call, so reserving budget for them would over-report what a resume costs.
    stage1_answer: dict[str, str | None] = {}
    stage1_state: dict[str, str] = {}

    for task in tasks:
        prompt = prompts["stage1"]["template"].format(task_prompt=task.prompt)
        req = model.build_request(prompt=prompt, system=systems["solver"], **common)
        entry = model.cache.get_raw(model.cache.make_key(req))
        if entry is None:
            needed["stage1"] += 1
            stage1_state[task.task_id] = "missing"
            stage1_answer[task.task_id] = None
        else:
            parsed = parse_response(entry.get("text", ""))
            stage1_answer[task.task_id] = parsed.answer
            stage1_state[task.task_id] = "ok" if parsed.parsed else "unparseable"

    for cond in cfg["conditions"]:
        spec = cond_specs[cond]
        if spec["kind"] == "single_turn":
            continue  # condition A reuses stage 1 and costs nothing
        sys_key = spec.get("system", "reviser")
        for task in tasks:
            state = stage1_state[task.task_id]
            if state == "unparseable":
                continue  # the runner skips these without calling
            if state == "missing":
                needed["stage2"] += 1  # depends on a stage-1 result not yet known
                continue
            prompt = spec["template"].format(
                task_prompt=task.prompt, initial_answer=stage1_answer[task.task_id],
                distractor_answer=task.distractor_answer)
            if not model.is_cached(prompt=prompt, system=systems[sys_key], **common):
                needed["stage2"] += 1

    if phase == "main":
        probes = cfg.get("probes", {})
        if probes.get("consistency", {}).get("enabled"):
            # The repeat re-issues the stage-1 prompt under a different
            # repetition index, so its key is known without running anything.
            n = min(probes["consistency"]["n_tasks"], len(tasks))
            count = 0
            for task in tasks[:n]:
                prompt = prompts["stage1"]["template"].format(task_prompt=task.prompt)
                for rep in range(1, probes["consistency"]["repeats"] + 1):
                    if not model.is_cached(prompt=prompt, system=systems["solver"],
                                           rep=rep, **common):
                        count += 1
            needed["consistency_probe"] = count

        ab = probes.get("prompt_ablation", {})
        if ab.get("enabled"):
            spec = prompts["ablations"][ab["name"]]
            sys_key = systems[spec.get("system", "reviser")]
            n = min(ab["n_tasks"], len(tasks))
            count = 0
            for task in tasks[:n]:
                state = stage1_state[task.task_id]
                if state == "unparseable":
                    continue  # skipped by the runner
                if state == "missing":
                    count += 1
                    continue
                prompt = spec["template"].format(
                    task_prompt=task.prompt,
                    initial_answer=stage1_answer[task.task_id],
                    distractor_answer=task.distractor_answer)
                if not model.is_cached(prompt=prompt, system=sys_key, **common):
                    count += 1
            needed["prompt_ablation"] = count

    needed["total"] = sum(needed.values())
    return needed


def _format_ok(p: Parsed, needs_assessment: bool) -> bool:
    """Did the reply satisfy the format the system prompt demanded?"""
    ok = p.answer is not None and p.confidence is not None
    if needs_assessment:
        ok = ok and p.assessment is not None
    return ok


def run_phase(cfg: dict[str, Any], prompts: dict[str, Any], phase: str,
              model: CachedModel, tasks: list[Task]) -> dict[str, Any]:
    mcfg = cfg["model"]
    conditions: list[str] = cfg["conditions"]
    cond_specs = prompts["conditions"]
    systems = prompts["system"]

    trials: list[TrialRecord] = []
    raw_log: list[dict[str, Any]] = []

    # ---- Stage 1: one call per task, shared across every condition ----
    stage1: dict[str, dict[str, Any]] = {}
    for i, task in enumerate(tasks, 1):
        prompt = prompts["stage1"]["template"].format(task_prompt=task.prompt)
        res = model.call(
            prompt=prompt, system=systems["solver"],
            temperature=mcfg["temperature"], max_output_tokens=mcfg["max_output_tokens"],
            seed=mcfg.get("seed"), thinking_budget=mcfg.get("thinking_budget"),
            condition="stage1", rep=0,
        )
        p = parse_response(res.text)
        stage1[task.task_id] = {
            "parsed": p, "result": res,
            "correct": is_correct(p.answer, task.answer),
            "format_ok": _format_ok(p, needs_assessment=False),
        }
        raw_log.append({
            "stage": "stage1", "task_id": task.task_id, "condition": "stage1",
            "family": task.family, "difficulty": task.difficulty,
            "prompt": prompt, "response": res.text, "ok": res.ok,
            "error": res.error, "from_cache": res.from_cache,
            "parsed_answer": p.answer, "confidence": p.confidence,
            "ground_truth": task.answer,
            "correct": is_correct(p.answer, task.answer),
        })
        print(f"  [stage1 {i}/{len(tasks)}] {task.task_id} "
              f"{'cache' if res.from_cache else 'live '} "
              f"ans={p.answer!r} truth={task.answer!r} "
              f"{'OK' if res.ok else 'FAIL:' + str(res.error)}", flush=True)

    # ---- Stage 2: one call per (task, intervention condition) ----
    for cond in conditions:
        spec = cond_specs[cond]
        if spec["kind"] == "single_turn":
            # Condition A reuses stage 1 verbatim; it costs no additional call.
            for task in tasks:
                s1 = stage1[task.task_id]
                p: Parsed = s1["parsed"]
                trials.append(TrialRecord(
                    task_id=task.task_id, family=task.family,
                    difficulty=task.difficulty, condition=cond,
                    initial_parsed=p.parsed, initial_correct=s1["correct"],
                    initial_answer=p.answer,
                    final_parsed=p.parsed, final_correct=s1["correct"],
                    final_answer=p.answer, assessment=None,
                    initial_confidence=p.confidence, final_confidence=p.confidence,
                    format_ok=s1["format_ok"], changed_answer=False,
                    error=s1["result"].error,
                ))
            continue

        sys_key = spec.get("system", "reviser")
        needs_assessment = "ASSESSMENT" in systems[sys_key]
        for i, task in enumerate(tasks, 1):
            s1 = stage1[task.task_id]
            p1: Parsed = s1["parsed"]
            if not p1.parsed:
                # No initial answer to intervene on. Record the trial as
                # unusable rather than fabricating an initial answer string.
                trials.append(TrialRecord(
                    task_id=task.task_id, family=task.family,
                    difficulty=task.difficulty, condition=cond,
                    initial_parsed=False, initial_correct=None, initial_answer=None,
                    final_parsed=False, final_correct=None, final_answer=None,
                    assessment=None, initial_confidence=None, final_confidence=None,
                    format_ok=False, changed_answer=None,
                    error="stage1_unparseable",
                ))
                continue

            prompt = spec["template"].format(
                task_prompt=task.prompt,
                initial_answer=p1.answer,
                distractor_answer=task.distractor_answer,
            )
            res = model.call(
                prompt=prompt, system=systems[sys_key],
                temperature=mcfg["temperature"],
                max_output_tokens=mcfg["max_output_tokens"],
                seed=mcfg.get("seed"), thinking_budget=mcfg.get("thinking_budget"),
                condition=cond, rep=0,
            )
            p2 = parse_response(res.text)
            final_correct = is_correct(p2.answer, task.answer)
            changed = None if (p2.answer is None or p1.answer is None) else (p2.answer != p1.answer)

            trials.append(TrialRecord(
                task_id=task.task_id, family=task.family,
                difficulty=task.difficulty, condition=cond,
                initial_parsed=True, initial_correct=s1["correct"],
                initial_answer=p1.answer,
                final_parsed=p2.parsed, final_correct=final_correct,
                final_answer=p2.answer, assessment=p2.assessment,
                initial_confidence=p1.confidence, final_confidence=p2.confidence,
                format_ok=_format_ok(p2, needs_assessment), changed_answer=changed,
                error=res.error,
            ))
            raw_log.append({
                "stage": "stage2", "task_id": task.task_id, "condition": cond,
                "family": task.family, "difficulty": task.difficulty,
                "prompt": prompt, "response": res.text, "ok": res.ok,
                "error": res.error, "from_cache": res.from_cache,
                "initial_answer": p1.answer, "parsed_answer": p2.answer,
                "assessment": p2.assessment, "confidence": p2.confidence,
                "ground_truth": task.answer, "distractor": task.distractor_answer,
                "correct": final_correct,
            })
            print(f"  [{cond} {i}/{len(tasks)}] {task.task_id} "
                  f"{'cache' if res.from_cache else 'live '} "
                  f"{p1.answer!r}->{p2.answer!r} truth={task.answer!r} "
                  f"assess={p2.assessment}", flush=True)

    return {"trials": [t.__dict__ for t in trials], "raw_log": raw_log}


def run_probes(cfg: dict[str, Any], prompts: dict[str, Any],
               model: CachedModel, tasks: list[Task]) -> dict[str, Any]:
    """Consistency repeat and the alternative-wording ablation."""
    mcfg = cfg["model"]
    probes = cfg.get("probes", {})
    out: dict[str, Any] = {}

    if probes.get("consistency", {}).get("enabled"):
        n = min(probes["consistency"]["n_tasks"], len(tasks))
        pairs = []
        for task in tasks[:n]:
            prompt = prompts["stage1"]["template"].format(task_prompt=task.prompt)
            base = model.call(
                prompt=prompt, system=prompts["system"]["solver"],
                temperature=mcfg["temperature"],
                max_output_tokens=mcfg["max_output_tokens"],
                seed=mcfg.get("seed"), thinking_budget=mcfg.get("thinking_budget"),
                condition="stage1", rep=0)  # cached from the main phase
            rep = model.call(
                prompt=prompt, system=prompts["system"]["solver"],
                temperature=mcfg["temperature"],
                max_output_tokens=mcfg["max_output_tokens"],
                seed=mcfg.get("seed"), thinking_budget=mcfg.get("thinking_budget"),
                condition="consistency_probe", rep=1)
            a = parse_response(base.text).answer
            b = parse_response(rep.text).answer
            pairs.append({"task_id": task.task_id, "rep0": a, "rep1": b,
                          "agree": (a == b) if (a is not None and b is not None) else None})
            print(f"  [consistency] {task.task_id} {a!r} vs {b!r}", flush=True)
        out["consistency"] = pairs

    ab = probes.get("prompt_ablation", {})
    if ab.get("enabled"):
        spec = prompts["ablations"][ab["name"]]
        n = min(ab["n_tasks"], len(tasks))
        rows = []
        for task in tasks[:n]:
            s1_prompt = prompts["stage1"]["template"].format(task_prompt=task.prompt)
            s1 = model.call(
                prompt=s1_prompt, system=prompts["system"]["solver"],
                temperature=mcfg["temperature"],
                max_output_tokens=mcfg["max_output_tokens"],
                seed=mcfg.get("seed"), thinking_budget=mcfg.get("thinking_budget"),
                condition="stage1", rep=0)
            p1 = parse_response(s1.text)
            if not p1.parsed:
                continue
            prompt = spec["template"].format(
                task_prompt=task.prompt, initial_answer=p1.answer,
                distractor_answer=task.distractor_answer)
            res = model.call(
                prompt=prompt, system=prompts["system"][spec.get("system", "reviser")],
                temperature=mcfg["temperature"],
                max_output_tokens=mcfg["max_output_tokens"],
                seed=mcfg.get("seed"), thinking_budget=mcfg.get("thinking_budget"),
                condition=ab["name"], rep=0)
            p2 = parse_response(res.text)
            rows.append({
                "task_id": task.task_id, "family": task.family,
                "difficulty": task.difficulty,
                "initial_answer": p1.answer, "final_answer": p2.answer,
                "assessment": p2.assessment,
                "initial_correct": is_correct(p1.answer, task.answer),
                "final_correct": is_correct(p2.answer, task.answer),
                "ground_truth": task.answer,
            })
            print(f"  [ablation {ab['name']}] {task.task_id} "
                  f"{p1.answer!r}->{p2.answer!r}", flush=True)
        out["prompt_ablation"] = {"name": ab["name"], "rows": rows}

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the alignment-invariants experiment.")
    ap.add_argument("--config", default="configs/experiment.yaml")
    ap.add_argument("--prompts", default="configs/prompts.yaml")
    ap.add_argument("--phase", choices=["pilot", "main"], default="main")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the call plan and exit without contacting the API.")
    ap.add_argument("--offline", action="store_true",
                    help="Serve only from cache; abort on any cache miss.")
    ap.add_argument("--mock", action="store_true",
                    help="Use the deterministic mock provider (pipeline testing only).")
    ap.add_argument("--max-calls", type=int, default=None,
                    help="Override the hard cap downward for this run.")
    args = ap.parse_args(argv)

    _load_dotenv()
    cfg = _load_yaml(args.config)
    prompts = _load_yaml(args.prompts)

    tasks = select_pilot_tasks(cfg) if args.phase == "pilot" else select_eval_tasks(cfg)
    plan = plan_calls(cfg, len(tasks), args.phase)

    cap = cfg["budget"]["max_api_calls"]
    if args.max_calls is not None:
        cap = min(cap, args.max_calls)

    # The per-run cap above bounds this process only. The study budget is
    # cumulative across every run ever made, which is what the ledger tracks.
    ledger = BudgetLedger(cfg["paths"].get("ledger", DEFAULT_LEDGER),
                          hard_cap=cfg["budget"]["max_api_calls"])

    print(f"\n=== phase={args.phase}  tasks={len(tasks)}  conditions={len(cfg['conditions'])} ===")
    print("Planned live calls (worst case, before cache):")
    for k, v in plan.items():
        print(f"  {k:22s} {v:4d}")
    print(f"  {'per-run cap':22s} {cap:4d}")
    print("Cumulative study budget (persists across runs):")
    print(f"  {'already spent':22s} {ledger.total_calls():4d}   {ledger.total_by_kind()}")
    print(f"  {'remaining':22s} {ledger.remaining():4d} of {ledger.hard_cap}")

    model_name = os.environ.get("GEMINI_MODEL") or cfg["model"]["name"]
    cache = ResponseCache(cfg["paths"]["cache_dir"])

    # Build the model first so the resume planner can derive cache keys exactly
    # the way the call path does.
    provider: Any
    provider_kind: str
    if args.mock:
        from src.gemini.mock import MockProvider
        provider = MockProvider({t.prompt: t.answer for t in tasks})
        provider_kind = "mock"
    elif args.offline:
        provider, provider_kind = None, "offline-cache"
    else:
        key = load_api_key()
        if not key:
            print("\nERROR: GEMINI_API_KEY is not set. Copy .env.example to .env "
                  "and add a key from https://aistudio.google.com/apikey\n"
                  "To exercise the pipeline without a key, use --mock or --offline.",
                  file=sys.stderr)
            return 3
        try:
            provider = GeminiProvider(key, timeout_s=cfg["model"].get("timeout_s", 60))
        except APIKeyError as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 3
        provider_kind = "gemini"

    # A real run may never push cumulative spend past the study cap, so its
    # guard is bounded by whatever the ledger has left. Mock and offline runs
    # issue no requests to the provider and are not charged, so bounding them
    # by the study budget would block pipeline testing for no benefit.
    spends_quota = provider_kind == "gemini"
    guard = BudgetGuard(max_calls=min(cap, ledger.remaining()) if spends_quota else cap)
    model = CachedModel(provider, cache, guard, model_name,
                        offline=(provider_kind == "offline-cache"),
                        namespace="mock" if provider_kind == "mock" else "gemini")

    resume = plan_live_calls(cfg, prompts, args.phase, model, tasks)
    already = plan["total"] - resume["total"]
    breakdown = {k: v for k, v in resume.items() if k != "total"}
    print("Actually needed now (cache-aware):")
    print(f"  {'already cached':22s} {already:4d}")
    print(f"  {'live calls needed':22s} {resume['total']:4d}   {breakdown}")

    if resume["total"] > cap:
        print(f"\nABORT: {resume['total']} live calls needed exceeds the per-run cap "
              f"of {cap}. Nothing was spent.", file=sys.stderr)
        return 2
    if spends_quota:
        try:
            ledger.check_can_spend(resume["total"])
        except LedgerExceededError as exc:
            print(f"\nABORT: {exc}\n"
                  f"Nothing was spent. Completed work is cached and this run is "
                  f"resumable once the study cap allows it.", file=sys.stderr)
            return 2
    if args.dry_run:
        print("\n--dry-run: no API calls issued.")
        return 0

    started = datetime.now(timezone.utc).isoformat()
    try:
        payload = run_phase(cfg, prompts, args.phase, model, tasks)
        if args.phase == "main":
            payload["probes"] = run_probes(cfg, prompts, model, tasks)
    except BudgetExceededError as exc:
        print(f"\nSTOPPED ON BUDGET: {exc}", file=sys.stderr)
        payload = {"trials": [], "raw_log": [], "aborted": str(exc)}
    except QuotaExhaustedError as exc:
        # Not an error in the experiment: the free-tier window is spent. Every
        # successful call is already cached, so re-running after the quota
        # resets continues from here instead of starting over.
        print(f"\nPAUSED ON QUOTA: {exc}\n"
              f"Re-run the same command after the quota window resets; cached "
              f"calls will not be repeated.", file=sys.stderr)
        payload = {"trials": [], "raw_log": [], "paused": str(exc)}
    except APIKeyError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 3

    # Debit the ledger before writing anything, so the results file records the
    # true post-run cumulative total and a crash after this point still leaves
    # the spend accounted for.
    _b = guard.summary()
    split = cfg["dataset"].get(f"{args.phase}_split", args.phase)
    if provider_kind == "gemini" and _b["api_requests"]:
        # Debit requests, not calls. A call retried through a rate limit issued
        # several requests and the free-tier quota is charged per request, so
        # debiting calls would understate real usage exactly when the run is
        # struggling against the quota.
        ledger.record(kind=args.phase, label=split, calls=_b["api_requests"],
                      successful=_b["successful_calls"], failed=_b["failed_calls"],
                      note=f"model={model_name}, phase={args.phase}, "
                           f"logical_calls={_b['live_calls']}")

    payload["meta"] = {
        "experiment_name": cfg["experiment_name"],
        "phase": args.phase,
        "provider": provider_kind,
        "model": model_name if provider_kind == "gemini" else f"MOCK({model_name})",
        "is_real_model_output": provider_kind in ("gemini", "offline-cache"),
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "n_tasks": len(tasks),
        "planned_calls": plan,
        "budget": guard.summary(),
        "cache": cache.stats(),
        # Cumulative spend across every run, not just this process. A results
        # file that reported only the per-run count implied far more budget
        # remained than actually did.
        "cumulative_budget": ledger.totals(),
    }
    payload["tasks"] = [t.to_dict() for t in tasks]

    out_dir = Path(cfg["paths"]["results_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if provider_kind != "mock" else "_MOCK"
    out_path = out_dir / f"{args.phase}_results{suffix}.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    b = guard.summary()
    # Debit the ledger with what this run actually spent, so the next run starts
    # from the true cumulative total even if this one crashed partway.
    print(f"\n--- budget ---")
    print(f"  live calls      : {b['live_calls']} / {b['max_calls']} (this run)")
    print(f"  successful      : {b['successful_calls']}")
    print(f"  failed          : {b['failed_calls']}")
    print(f"  cache hits      : {b['cache_hits']}")
    print(f"  tokens (p/o)    : {b['prompt_tokens']} / {b['output_tokens']}")
    print(f"  per condition   : {b['calls_per_condition']}")
    print(f"\n--- cumulative study budget ---")
    t = ledger.totals()
    print(f"  spent all runs  : {t['total_calls']} / {t['hard_cap']}")
    print(f"  remaining       : {t['remaining']}")
    print(f"  by kind         : {t['by_kind']}")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
