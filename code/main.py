"""Buy or Wait? - entrypoint.

Reads dataset/requests.csv, builds each request's UserFinancialContext via
ingest, runs the deterministic forecaster, and writes the deliverable
output.csv at the repo root.

Run:  python code/main.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from ingest import load_requests, load_user_context
from forecasting import decide
from models import Decision

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "output.csv"


def main() -> None:
    requests = load_requests()
    rows = []
    for req in requests:
        context = load_user_context(req["request_id"])
        rows.append(decide(context))

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(Decision.HEADER)
        writer.writerows(d.to_row() for d in rows)

    print(f"wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()


