"""Dump settled cash history by category for two users (calibration aid).

Run:  python code/tests/diag_recurring.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import load_sample_requests, load_user_context  # noqa: E402

TARGETS = {"user_02": "request_02", "user_03": "request_03"}


def main() -> None:
    by_user = {r["user_id"]: r["request_id"] for r in load_sample_requests()}
    for user_id, request_id in TARGETS.items():
        ctx = load_user_context(request_id)
        start = ctx.request.request_date
        print(f"=== {user_id} (request_date={start.isoformat()}) ===")
        groups = defaultdict(list)
        for e in ctx.events:
            if e.tag.value not in ("cash_in", "cash_out", "pending_debit_reserve"):
                continue
            when = e.settlement_date or e.event_date
            groups[(e.tag.value, e.direction, e.category)].append((when, e.amount_home))
        for key in sorted(groups):
            tag, direction, category = key
            occ = sorted(groups[key])
            dates = [d.isoformat() for d, _ in occ]
            amounts = [a for _, a in occ]
            gaps = [
                (dates[i + 1] and (date.fromisoformat(dates[i + 1]) - date.fromisoformat(dates[i])).days)
                for i in range(len(dates) - 1)
            ]
            print(
                f"  [{tag}/{direction}] {category}: n={len(occ)} "
                f"dates={','.join(dates[-6:])} amounts={amounts[-4:]} gaps={gaps[-3:]}"
            )
        print()


if __name__ == "__main__":
    main()
