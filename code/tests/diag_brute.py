"""Brute-force the generator's per-category amount statistic.

Equations (derived from the solved samples):
  user_02 (2025-08-05..2025-08-14): utilities+groceries+healthcare+transport
    [+entertainment if stepping by +30d] == 12,345,250 - fixed_sum
  user_03 (2019-09-03..2019-09-14): utilities+groceries+shopping+dining
    == 2,173,600 - (rent+pending+streaming+cloud)

Run:  python code/tests/diag_brute.py
"""

import itertools
import sys
from collections import defaultdict
from statistics import mean, median
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import load_user_context  # noqa: E402

STATS = {
    "last": lambda a: a[-1],
    "first": lambda a: a[0],
    "mean_all": lambda a: mean(a),
    "median_all": lambda a: median(a),
    "mean_last3": lambda a: mean(a[-3:]),
    "median_last3": lambda a: median(a[-3:]),
}


def category_amounts(request_id, categories):
    ctx = load_user_context(request_id)
    start = ctx.request.request_date
    groups = defaultdict(list)
    for e in ctx.events:
        if e.tag.value not in ("cash_in", "cash_out"):
            continue
        when = e.settlement_date or e.event_date
        if when and when < start and e.amount_home and e.category in categories:
            groups[e.category].append((when, e.amount_home))
    return {c: [a for _, a in sorted(v)] for c, v in groups.items()}


def solve(label, fixed_total, target, variable_categories, amounts):
    budget = target - fixed_total
    print(f"--- {label}: budget for {variable_categories} = {budget:,.2f} ---")
    stats_by_cat = {
        c: {name: fn(amounts[c]) for name, fn in STATS.items()}
        for c in variable_categories
    }
    names = list(STATS)
    found = 0
    for combo in itertools.product(names, repeat=len(variable_categories)):
        total = sum(stats_by_cat[c][s] for c, s in zip(variable_categories, combo))
        if abs(total - budget) < 0.01:
            found += 1
            print("  MATCH:", ", ".join(f"{c}={s}" for c, s in zip(variable_categories, combo)))
    if not found:
        for c in variable_categories:
            print(f"  {c}: " + ", ".join(f"{s}={stats_by_cat[c][s]:,.2f}" for s in names))
    print()


def main() -> None:
    u2 = category_amounts(
        "request_02",
        {"utilities", "groceries", "healthcare", "transport", "entertainment"},
    )
    u3 = category_amounts("request_03", {"utilities", "groceries", "shopping", "dining"})

    # user_02 T1 fixed parts: insurance + pending + education + cloud
    fixed2 = 1132400.0 + 1651100.0 + 3040000.0 + 369550.0
    solve(
        "user_02 A (entertainment inside, +30d)",
        fixed2,
        12345250.0,
        ["utilities", "groceries", "healthcare", "transport", "entertainment"],
        u2,
    )
    solve(
        "user_02 B (entertainment outside, calendar)",
        fixed2,
        12345250.0,
        ["utilities", "groceries", "healthcare", "transport"],
        u2,
    )

    # user_03 T1 fixed parts: rent + pending + streaming + cloud
    fixed3 = 1140000.0 + 95000.0 + 117800.0 + 20900.0
    solve("user_03", fixed3, 2173600.0, ["utilities", "groceries", "shopping", "dining"], u3)


if __name__ == "__main__":
    main()
