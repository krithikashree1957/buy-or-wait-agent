"""Compare deterministic forecasts against the solved samples (first 3).

For each sample request prints our fields next to the solved answer from
sample_requests.csv and reports exact-match or mismatch per field.

Run:  python code/tests/test_forecasting.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import load_sample_requests, load_user_context  # noqa: E402
from forecasting import decide  # noqa: E402

FIELDS = (
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
)


def main() -> None:
    for row in load_sample_requests()[:3]:
        ctx = load_user_context(row["request_id"])
        dec = decide(ctx)
        ours = {
            "amount_safe_to_pay": dec.amount_safe_to_pay,
            "affordability_status": dec.affordability_status.value,
            "recommended_payment_method": dec.recommended_payment_method.value,
            "payment_plan": dec.payment_plan,
            "earliest_date_for_full_payment": dec.earliest_date_for_full_payment,
        }
        print(f"=== {row['request_id']} / {ctx.request.user_id} ===")
        for f in FIELDS:
            expected = row.get(f, "") or ""
            match = "MATCH" if ours[f].strip() == expected.strip() else "MISMATCH"
            print(f"  {f}: ours={ours[f]!r} expected={expected!r} -> {match}")
        print()


if __name__ == "__main__":
    main()
