"""Resumability across free-tier quota resets.

The main experiment is larger than one free-tier quota window, so it has to run
across several sessions. That is only safe if three things hold, and each is
asserted here rather than assumed:

* a successful call is never issued twice, however many times the run restarts;
* a run that stops partway leaves the completed work usable, not orphaned;
* the cumulative ledger stays accurate across processes, including retries.
"""

from __future__ import annotations

import pytest
import yaml

from src.caching.cache import ResponseCache
from src.caching.ledger import BudgetLedger
from src.gemini.client import (BudgetGuard, CachedModel, CallResult,
                               QuotaExhaustedError)
from src.run_experiment import plan_live_calls, run_phase
from src.tasks.generators import generate_dataset


class ScriptedProvider:
    """Answers correctly, and can be told to start rate limiting partway."""

    def __init__(self, answers: dict[str, str], fail_after: int | None = None,
                 attempts_per_call: int = 1):
        self.answers = answers
        self.fail_after = fail_after
        self.attempts_per_call = attempts_per_call
        self.calls = 0
        self.seen: list[str] = []

    def generate(self, *, prompt: str, **kw):
        self.calls += 1
        self.seen.append(prompt)
        if self.fail_after is not None and self.calls > self.fail_after:
            return CallResult(text="", from_cache=False, ok=False,
                              error="rate_limited", attempts=4)
        ans = next((v for k, v in self.answers.items() if k in prompt), "1")
        return CallResult(text=f"FINAL: {ans}\nCONFIDENCE: 70",
                          from_cache=False, ok=True, prompt_tokens=5,
                          output_tokens=5, attempts=self.attempts_per_call)


@pytest.fixture
def setup(tmp_path):
    cfg = yaml.safe_load(open("configs/experiment.yaml", encoding="utf-8"))
    prompts = yaml.safe_load(open("configs/prompts.yaml", encoding="utf-8"))
    tasks = generate_dataset(seed=1, n_per_cell=1, split="resumetest",
                             families=("false_premise",), difficulties=(1,))
    answers = {t.prompt[:40]: t.answer for t in tasks}
    return cfg, prompts, tasks, answers, tmp_path


def build(tmp_path, provider, remaining=1000):
    cache = ResponseCache(tmp_path / "cache")
    guard = BudgetGuard(max_calls=remaining)
    return CachedModel(provider, cache, guard, "m", namespace="gemini"), guard, cache


class TestNoDuplicateCalls:
    def test_second_run_issues_no_calls_at_all(self, setup):
        cfg, prompts, tasks, answers, tmp_path = setup
        p1 = ScriptedProvider(answers)
        model, guard, _ = build(tmp_path, p1)
        run_phase(cfg, prompts, "pilot", model, tasks)
        first = p1.calls
        assert first > 0

        # A fresh process: new provider, new guard, same cache directory.
        p2 = ScriptedProvider(answers)
        model2, guard2, _ = build(tmp_path, p2)
        run_phase(cfg, prompts, "pilot", model2, tasks)
        assert p2.calls == 0, "a completed run re-issued calls on resume"
        assert guard2.live_calls == 0
        assert guard2.cache_hits == first

    def test_planner_reports_zero_after_a_complete_run(self, setup):
        cfg, prompts, tasks, answers, tmp_path = setup
        model, _, _ = build(tmp_path, ScriptedProvider(answers))
        before = plan_live_calls(cfg, prompts, "pilot", model, tasks)
        assert before["total"] > 0
        run_phase(cfg, prompts, "pilot", model, tasks)

        model2, _, _ = build(tmp_path, ScriptedProvider(answers))
        after = plan_live_calls(cfg, prompts, "pilot", model2, tasks)
        assert after["total"] == 0, f"resume would re-spend {after}"


class TestPartialRunResumes:
    def test_quota_stop_preserves_completed_work(self, setup):
        cfg, prompts, tasks, answers, tmp_path = setup
        # Allow a few calls, then rate limit.
        p1 = ScriptedProvider(answers, fail_after=3)
        model, guard, cache = build(tmp_path, p1)
        with pytest.raises(QuotaExhaustedError):
            run_phase(cfg, prompts, "pilot", model, tasks)
        assert cache.writes == 3, "successful calls before the stop were not kept"

        # The quota window resets: the same command continues from here.
        p2 = ScriptedProvider(answers)
        model2, guard2, _ = build(tmp_path, p2)
        run_phase(cfg, prompts, "pilot", model2, tasks)
        assert guard2.cache_hits == 3, "completed work was not reused"
        assert p2.calls > 0, "the remainder was never issued"

    def test_needed_count_shrinks_as_the_run_progresses(self, setup):
        cfg, prompts, tasks, answers, tmp_path = setup
        p1 = ScriptedProvider(answers, fail_after=2)
        model, _, _ = build(tmp_path, p1)
        total_before = plan_live_calls(cfg, prompts, "pilot", model, tasks)["total"]
        with pytest.raises(QuotaExhaustedError):
            run_phase(cfg, prompts, "pilot", model, tasks)
        model2, _, _ = build(tmp_path, ScriptedProvider(answers))
        total_after = plan_live_calls(cfg, prompts, "pilot", model2, tasks)["total"]
        assert total_after < total_before

    def test_failed_calls_are_retried_not_replayed(self, setup):
        """Requirement: successes are never repeated, failures always are."""
        cfg, prompts, tasks, answers, tmp_path = setup
        p1 = ScriptedProvider(answers, fail_after=0)  # everything fails
        model, _, cache = build(tmp_path, p1)
        with pytest.raises(QuotaExhaustedError):
            run_phase(cfg, prompts, "pilot", model, tasks)
        assert cache.writes == 0, "a failure was written to the cache"

        p2 = ScriptedProvider(answers)
        model2, guard2, _ = build(tmp_path, p2)
        run_phase(cfg, prompts, "pilot", model2, tasks)
        assert guard2.cache_hits == 0
        assert p2.calls > 0, "the failed call was not retried"


class TestLedgerAccuracy:
    def test_retries_are_debited_as_separate_requests(self, tmp_path):
        """A call retried through a rate limit consumed several requests, and
        the free-tier quota is charged per request."""
        guard = BudgetGuard(max_calls=10)
        guard.record(CallResult(text="x", from_cache=False, ok=True, attempts=3),
                     "stage1")
        assert guard.live_calls == 1
        assert guard.api_requests == 3

        led = BudgetLedger(tmp_path / "l.json", hard_cap=250)
        led.record(kind="main", label="eval", calls=guard.api_requests,
                   successful=guard.successful, failed=guard.failed)
        assert led.total_calls() == 3, "retries were not charged to the budget"

    def test_guard_is_bounded_by_remaining_study_budget(self, tmp_path):
        """Even with a generous per-run cap, a run may not overspend the study."""
        led = BudgetLedger(tmp_path / "l.json", hard_cap=250)
        led.record(kind="pilot", label="p", calls=245)
        guard = BudgetGuard(max_calls=min(250, led.remaining()))
        assert guard.max_calls == 5
