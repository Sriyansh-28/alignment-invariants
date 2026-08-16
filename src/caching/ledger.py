"""Persistent cumulative ledger of real API calls.

``BudgetGuard`` enforces a cap *within a single process*. That is not the same
thing as a study budget, and the difference was not academic: Pilots 1 and 2
each reported "48 live / 250 cap, 202 remaining" while between them consuming 96
real calls, because nothing carried the count across invocations. A reader of
either results file would conclude 202 calls were still available. This ledger
is the missing piece -- it survives separate runs, and every live call is
debited against one running total.

Design notes:

* The ledger is a committed JSON file, so the spend history is part of the
  experimental record rather than local state that vanishes with the container.
* Diagnostic and exploratory calls are recorded too. They consume the same
  quota as experimental calls, so a budget that ignores them is not a budget.
* Entries are append-only. Rewriting history would defeat the purpose, so the
  only supported mutation is appending a new entry.
* Failed calls are debited exactly like successful ones, because a rejected
  request still costs quota.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = "experiments/budget_ledger.json"


class LedgerExceededError(RuntimeError):
    """Raised when a run would push cumulative spend past the study cap."""


class BudgetLedger:
    def __init__(self, path: str | Path = DEFAULT_LEDGER, hard_cap: int = 250) -> None:
        self.path = Path(path)
        self.hard_cap = hard_cap
        self.data: dict[str, Any] = {"hard_cap": hard_cap, "entries": []}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                self.data = json.load(fh)
            # The cap lives in the file so a later run cannot quietly widen it
            # by passing a different value on the command line.
            self.hard_cap = self.data.get("hard_cap", hard_cap)

    # -- reading -----------------------------------------------------------

    def total_calls(self) -> int:
        return sum(e["calls"] for e in self.data["entries"])

    def total_by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.data["entries"]:
            out[e["kind"]] = out.get(e["kind"], 0) + e["calls"]
        return dict(sorted(out.items()))

    def totals(self) -> dict[str, int]:
        ent = self.data["entries"]
        return {
            "hard_cap": self.hard_cap,
            "total_calls": self.total_calls(),
            "successful": sum(e.get("successful", 0) for e in ent),
            "failed": sum(e.get("failed", 0) for e in ent),
            "remaining": self.remaining(),
            "by_kind": self.total_by_kind(),
            "entries": len(ent),
        }

    def remaining(self) -> int:
        return self.hard_cap - self.total_calls()

    # -- writing -----------------------------------------------------------

    def check_can_spend(self, n: int) -> None:
        if self.total_calls() + n > self.hard_cap:
            raise LedgerExceededError(
                f"refusing to start: {self.total_calls()} real API calls already "
                f"recorded across all runs, this run plans {n} more, study cap is "
                f"{self.hard_cap} ({self.remaining()} remaining)"
            )

    def record(self, *, kind: str, label: str, calls: int,
               successful: int = 0, failed: int = 0,
               note: str = "") -> dict[str, Any]:
        """Append one entry. ``kind`` is coarse (diagnostic/pilot/main)."""
        entry = {
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "label": label,
            "calls": calls,
            "successful": successful,
            "failed": failed,
            "note": note,
        }
        self.data["entries"].append(entry)
        self.data["hard_cap"] = self.hard_cap
        self._write()
        return entry

    def set_cap(self, new_cap: int, reason: str) -> None:
        """Change the study cap, leaving an audit entry.

        Deliberately awkward: the cap is the study's headline budget number, and
        a run that could quietly raise its own ceiling would not have a ceiling.
        Changing it is a research decision, so it takes an explicit call with a
        stated reason, recorded as a zero-call entry in the same history as the
        spending. Lowering the cap below what is already spent is refused --
        that would silently invalidate the record rather than constrain it.
        """
        if new_cap < self.total_calls():
            raise LedgerExceededError(
                f"cannot set cap to {new_cap}: {self.total_calls()} calls are "
                f"already recorded"
            )
        old = self.hard_cap
        self.hard_cap = new_cap
        self.data["hard_cap"] = new_cap
        self.data["entries"].append({
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": "cap_change", "label": f"{old} -> {new_cap}",
            "calls": 0, "successful": 0, "failed": 0, "note": reason,
        })
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Inspect or adjust the study budget ledger.")
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--set-cap", type=int, default=None,
                    help="Change the study cap. Requires --reason.")
    ap.add_argument("--reason", default="", help="Why the cap is changing.")
    args = ap.parse_args(argv)

    led = BudgetLedger(args.ledger)
    if args.set_cap is not None:
        if not args.reason.strip():
            print("ERROR: --set-cap requires --reason", file=__import__("sys").stderr)
            return 2
        led.set_cap(args.set_cap, args.reason.strip())
        print(f"cap set to {args.set_cap}")

    t = led.totals()
    print(f"study cap        : {t['hard_cap']}")
    print(f"spent (requests) : {t['total_calls']}")
    print(f"  successful     : {t['successful']}")
    print(f"  failed         : {t['failed']}")
    print(f"remaining        : {t['remaining']}")
    print(f"by kind          : {t['by_kind']}")
    print(f"entries          : {t['entries']}")
    for e in led.data["entries"]:
        print(f"  {e['utc']}  {e['kind']:12s} {e['label']:24s} {e['calls']:4d}  {e['note']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
