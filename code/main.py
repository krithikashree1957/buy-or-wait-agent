"""Buy or Wait? - entrypoint.

Reads dataset/requests.csv, builds each request's UserFinancialContext via
ingest, runs the deterministic forecaster, applies spending-change planning,
adds the LLM judgment explanation (Stage 5.2), and writes the deliverable
output.csv at the repo root. Any single-request failure is logged and a safe
conservative fallback row (not_affordable / not_recommended) is written so one
bad request can never crash the run.

Run:  python code/main.py
"""

from __future__ import annotations

import csv
import json
import time
import traceback
from pathlib import Path

from forecasting import decide
from ingest import load_requests, load_user_context
from judgment import USAGE, decision_explanation
from models import AffordabilityStatus, Decision, PaymentMethod

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "output.csv"
USAGE_DUMP_PATH = REPO_ROOT / "code" / "evaluation" / "usage_data.json"


def fallback_row(request_id: str) -> Decision:
    """Schema-valid conservative row when a request cannot be decided."""
    return Decision(
        request_id=request_id,
        amount_safe_to_pay="0",
        affordability_status=AffordabilityStatus.NOT_AFFORDABLE,
        recommended_payment_method=PaymentMethod.NOT_RECOMMENDED,
        payment_plan="none",
        earliest_date_for_full_payment="",
        spending_changes_needed="none",
        decision_explanation="fallback: processing error",
    )


def main() -> None:
    requests = load_requests()
    rows: list[Decision] = []
    failures: list[tuple[str, str]] = []
    started = time.perf_counter()
    for req in requests:
        request_id = (req.get("request_id") or "").strip()
        try:
            context = load_user_context(request_id)
            decision = decide(context)
            decision = decision_explanation(context, decision)
            rows.append(decision)
        except Exception as exc:  # keep the run alive; log and fall back
            traceback.print_exc()
            failures.append((request_id, f"{type(exc).__name__}: {exc}"))
            rows.append(fallback_row(request_id))
    elapsed = time.perf_counter() - started

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(Decision.HEADER)
        writer.writerows(d.to_row() for d in rows)

    USAGE_DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    USAGE_DUMP_PATH.write_text(json.dumps(USAGE, indent=2), encoding="utf-8")

    print(f"wrote {len(rows)} rows to {OUTPUT_PATH} in {elapsed:.1f}s")
    print(f"fallback rows: {len(failures)}/{len(rows)}")
    for rid, why in failures:
        print(f"  FAILED {rid}: {why}")
    if USAGE:
        total_in = sum(u["input_tokens"] for u in USAGE)
        total_out = sum(u["output_tokens"] for u in USAGE)
        print(f"LLM calls: {len(USAGE)}  tokens in/out: {total_in}/{total_out}")
    else:
        print("LLM calls: 0 (deterministic explanations; no OPENAI_API_KEY set)")


if __name__ == "__main__":
    main()


