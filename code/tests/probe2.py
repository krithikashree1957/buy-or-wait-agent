"""Probe user_02/user_03 events + messages to explain Stage 4 mismatches."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import load_user_context  # noqa: E402


def main() -> None:
    for rid in ("request_02", "request_03"):
        ctx = load_user_context(rid)
        req = ctx.request
        p = ctx.profile
        print(f"### {rid} src={ctx.request_source}")
        print(f"req date={req.request_date} amt={req.requested_amount} "
              f"deadline={req.desired_completion_date} partial={req.allows_partial_payment}")
        print(f"bal={p.current_available_balance} minkeep={p.minimum_balance_to_keep} "
              f"methods={p.payment_methods_user_will_consider} maxinst={p.max_installment_months}")
        print("-- events (tag, dir, status, type, category, flex, event_date, settle, amount_home, linked):")
        for e in sorted(ctx.events, key=lambda x: (x.settlement_date or x.event_date or x.event_date)):
            w = e.settlement_date or e.event_date
            print(f"{e.event_id} {e.tag.value} {e.direction} {e.status} {e.event_type} "
                  f"{e.category} {e.flexibility} ev={e.event_date} st={e.settlement_date} "
                  f"amt={e.amount_home} link={e.linked_event_id}")
        print("-- messages:")
        for m in ctx.user_messages:
            print({k: v for k, v in m.items() if v and k in
                   ("message_id", "related_event_id", "date", "message_text")})
        print()


if __name__ == "__main__":
    main()
