"""Buy or Wait? - entrypoint.

Reads dataset/requests.csv, produces one schema-valid row per request, and
writes the deliverable output.csv at the repo root.

Run:  python code/main.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from ingest import (
    load_exchange_rates,
    load_financial_events,
    load_financial_profiles,
    load_images,
    load_messages,
    load_request_payment_options,
    load_requests,
)
from models import Decision
from forecasting import decide
from vision import extract_amount_from_image

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "output.csv"


def placeholder_decision(request: dict[str, str]) -> Decision:
    """Dummy-but-schema-valid row used until the real logic lands."""
    return Decision(
        request_id=request["request_id"],
        decision_explanation="placeholder: decision logic not yet implemented",
    )


def main() -> None:
    requests = load_requests()
    profiles = {p.get("user_id", ""): p for p in load_financial_profiles()}
    events = load_financial_events()
    options = load_request_payment_options()
    rates = load_exchange_rates()
    messages = load_messages()
    images = load_images()

    rows: list[Decision] = []
    for request in requests:
        try:
            decision = decide(
                request=request,
                profile=profiles.get(request.get("user_id", ""), {}),
                events=[e for e in events if e.get("user_id") == request.get("user_id")],
                options=[
                    o
                    for o in options
                    if o.get("request_id") == request.get("request_id")
                ],
                exchange_rates=rates,
                messages=messages,
                images=images,
                extract_amount=extract_amount_from_image,
            )
        except NotImplementedError:
            decision = placeholder_decision(request)
        rows.append(decision)

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(Decision.HEADER)
        writer.writerows(d.to_row() for d in rows)

    print(f"wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

