"""Verify ingest exclusion rules against the raw dataset (evidence, not asserts).

Checks:
1. every status=failed / status=unrealized row gets an excluded_* tag
   (i.e. never cash_in/cash_out) - with examples
2. 'duplicate' status absent from raw data (defensive branch only)
3. every status=pending credit row is excluded_pending_credit - with examples

Run:  python code/tests/verify_exclusions.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import FxTable, build_event  # noqa: E402

DATASET = Path(__file__).resolve().parents[2] / "dataset"


def main() -> None:
    with (DATASET / "financial_events.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    fx = FxTable([])

    def tag_of(row: dict[str, str]):
        # home = row's own currency -> native conversion, so this test
        # exercises tagging only (FX correctness is separate).
        return build_event(
            row, (row.get("currency") or "ZZZ").strip().upper(), fx, {}, lambda p: None
        )

    statuses = Counter((r.get("status") or "").strip() for r in rows)
    print("distinct statuses in raw data:", dict(sorted(statuses.items())))
    print("check2 'duplicate' status present:", "duplicate" in statuses)

    for status in ("failed", "unrealized"):
        subset = [r for r in rows if (r.get("status") or "").strip().lower() == status]
        excluded = []
        leaked = []
        for r in subset:
            rec = tag_of(r)
            if rec.tag.value.startswith("excluded_"):
                excluded.append(
                    f"{rec.event_id} ({r.get('event_type')}/{r.get('direction')}) -> {rec.tag.value}"
                )
            else:
                leaked.append((rec.event_id, rec.tag.value))
        print(
            f"check1 status={status}: n={len(subset)} excluded_ok={len(excluded)} "
            f"leaked={leaked or 'none'} examples={excluded[:2]}"
        )

    pend_ok = []
    pend_bad = []
    n_pend_credit = 0
    for r in rows:
        if (r.get("status") or "").strip().lower() != "pending":
            continue
        if (r.get("direction") or "").strip().lower() != "credit":
            continue
        n_pend_credit += 1
        rec = tag_of(r)
        if rec.tag.value == "excluded_pending_credit":
            pend_ok.append(f"{rec.event_id} ({r.get('event_type')})")
        else:
            pend_bad.append((rec.event_id, rec.tag.value))
    print(
        f"check3 pending credits: n={n_pend_credit} excluded_ok={len(pend_ok)} "
        f"not_excluded={pend_bad or 'none'} examples={pend_ok[:3]}"
    )


if __name__ == "__main__":
    main()
