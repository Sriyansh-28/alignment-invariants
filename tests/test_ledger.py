"""Cumulative budget ledger.

The failure this guards against is concrete: Pilots 1 and 2 each reported
"48 live / 250 cap, 202 remaining" while together consuming 96 real calls,
because BudgetGuard counts within one process and nothing carried across runs.
Anyone reading either results file would have believed 202 calls remained.
"""

from __future__ import annotations

import pytest

from src.caching.ledger import BudgetLedger, LedgerExceededError


def test_totals_accumulate_across_instances(tmp_path):
    path = tmp_path / "ledger.json"
    a = BudgetLedger(path, hard_cap=250)
    a.record(kind="pilot", label="pilot1", calls=48, successful=48)
    # A fresh instance stands in for a separate process, which is the case the
    # per-run guard could not see.
    b = BudgetLedger(path, hard_cap=250)
    b.record(kind="pilot", label="pilot2", calls=48, successful=48)
    c = BudgetLedger(path, hard_cap=250)
    assert c.total_calls() == 96
    assert c.remaining() == 154


def test_diagnostic_calls_are_counted(tmp_path):
    """Exploratory calls consume the same quota; a budget that ignores them is
    not a budget."""
    led = BudgetLedger(tmp_path / "l.json", hard_cap=100)
    led.record(kind="diagnostic", label="probe", calls=7, successful=5, failed=2)
    led.record(kind="pilot", label="p", calls=10, successful=10)
    assert led.total_calls() == 17
    assert led.total_by_kind() == {"diagnostic": 7, "pilot": 10}


def test_failed_calls_are_debited(tmp_path):
    led = BudgetLedger(tmp_path / "l.json", hard_cap=100)
    led.record(kind="pilot", label="p", calls=5, successful=2, failed=3)
    t = led.totals()
    assert t["total_calls"] == 5 and t["failed"] == 3 and t["successful"] == 2


def test_check_refuses_a_run_that_would_exceed_the_cap(tmp_path):
    led = BudgetLedger(tmp_path / "l.json", hard_cap=50)
    led.record(kind="pilot", label="p", calls=40, successful=40)
    led.check_can_spend(10)  # exactly to the cap is allowed
    with pytest.raises(LedgerExceededError):
        led.check_can_spend(11)


def test_cap_cannot_be_widened_by_a_later_run(tmp_path):
    """The cap is persisted, so a later invocation passing a bigger number
    cannot quietly raise the study budget."""
    path = tmp_path / "l.json"
    BudgetLedger(path, hard_cap=250).record(kind="pilot", label="p", calls=1)
    assert BudgetLedger(path, hard_cap=99999).hard_cap == 250


def test_entries_are_append_only(tmp_path):
    path = tmp_path / "l.json"
    led = BudgetLedger(path, hard_cap=250)
    for i in range(3):
        led.record(kind="pilot", label=f"p{i}", calls=1)
    assert len(BudgetLedger(path).data["entries"]) == 3


def test_repo_ledger_accounts_for_every_prior_run():
    """The committed ledger must reflect real spend to date, not a fresh start.
    If this drifts, the remaining-budget figure in every report is wrong."""
    led = BudgetLedger()
    assert led.hard_cap == 250
    assert led.total_calls() > 0, "ledger was never seeded with prior spend"
    kinds = led.total_by_kind()
    assert "diagnostic" in kinds, "diagnostic calls are missing from the ledger"
    assert "pilot" in kinds
    assert led.total_calls() == sum(kinds.values())
