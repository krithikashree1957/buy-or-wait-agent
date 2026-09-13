"""Solve the generator's recurring-amount statistic against known targets.

Targets (reverse-engineered from sample_requests.csv solved answers):
  user_02: total projected outflow 2025-08-05..2025-08-14 == 12,345,250
  user_03: total projected outflow 2019-09-03..2019-09-14 == 2,173,600

Run:  python code/tests/diag_stat.py
"""

from __future__ import annotations

import calendar
import sys
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import load_user_context  # noqa: E402

TARGETS = {"request_02": (date(2025, 8, 5), date(2025, 8, 14), 12345250.0),
           "request_03": (date(2019, 9, 3), date(2019, 9, 14), 2173600.0)}
STATS = {
    "last": lambda a: a[-1],
    "first": lambda a: a[0],
    "mean_all": lambda a: mean(a),
    "median_all": lambda a: median(a),
    "mean_last3": lambda a: mean(a[-3:]),
    "median_last3": lambda a: median(a[-3:]),
}


def add_months(d: date, k: int) -> date:
    month_index = d.year * 12 + (d.month - 1) + k
    y, m = divmod(month_index, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def next_dates(last: date, gap: int, window_end: date):
    out = []
    t = last
    while True:
        t = add_months(t, 1) if gap >= 28 else t + timedelta(days=gap)
        if t > window_end:
            return out
        out.append(t)


def window_flows(ctx, stat, window_start, window_end):
    groups = defaultdict(list)
    for e in ctx.events:
        if e.tag.value not in ("cash_in", "cash_out"):
            continue
        when = e.settlement_date or e.event_date
        if when and when < window_start and e.amount_home:
            groups[(e.direction, e.category)].append((when, e.amount_home))
    flows = {}
    for key, occ in groups.items():
        direction, category = key
        occ.sort()
        dates = [d for d, _ in occ]
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gap = int(round(median(gaps))) if gaps else 30
        if not (5 <= gap <= 45):
            continue
        amount = stat([a for _, a in occ])
        sign = 1.0 if direction == "credit" else -1.0
        for t in next_dates(dates[-1], gap, window_end):
            if t >= window_start:
                flows[t] = flows.get(t, 0.0) + sign * amount
    for e in ctx.events:
        if e.tag.value == "pending_debit_reserve":
            when = max(e.settlement_date or e.event_date, window_start)
            if when <= window_end:
                flows[when] = flows.get(when, 0.0) - (e.amount_home or 0.0)
    return flows


def main() -> None:
    for request_id, (ws, we, target) in TARGETS.items():
        ctx = load_user_context(request_id)
        print(f"=== {request_id} target T1={target:,.2f} ===")
        for name, fn in STATS.items():
            def stat(amounts, _fn=fn):
                return _fn(amounts)
            groups = defaultdict(list)
            for e in ctx.events:
                if e.tag.value not in ("cash_in", "cash_out"):
                    continue
                when = e.settlement_date or e.event_date
                if when and when < ws and e.amount_home:
                    groups[(e.direction, e.category)].append((when, e.amount_home))
            stats_map = {k: stat([a for _, a in sorted(v)]) for k, v in groups.items()}
            flows = window_flows(ctx, stat, ws, we)
            total = sum(v for d, v in flows.items() if ws <= d <= we)
            print(f"  {name:14s} T1={total:,.2f} {'<-- MATCH' if abs(total-target) < 0.01 else ''}")
        print()


if __name__ == "__main__":
    main()
