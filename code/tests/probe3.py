"""Probe3: ASCII output; income clusters + flows for request_02/03."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import load_user_context  # noqa: E402
import forecasting as F  # noqa: E402

OUT = Path(__file__).with_name("probe3_out.txt")


def main() -> None:
    lines = []
    for rid in ("request_02", "request_03"):
        ctx = load_user_context(rid)
        req, p = ctx.request, ctx.profile
        lines.append(f"### {rid} src={ctx.request_source}")
        lines.append(f"req date={req.request_date} amt={req.requested_amount} "
                     f"deadline={req.desired_completion_date} partial={req.allows_partial_payment}")
        lines.append(f"bal={p.current_available_balance} minkeep={p.minimum_balance_to_keep} "
                     f"methods={p.payment_methods_user_will_consider} maxinst={p.max_installment_months}")
        lines.append("-- CREDIT events (all, sorted):")
        for e in sorted((e for e in ctx.events if e.direction == "credit"),
                        key=lambda x: (x.settlement_date or x.event_date)):
            lines.append(f"{e.event_id} {e.tag.value} {e.status} {e.event_type} {e.category} "
                         f"ev={e.event_date} st={e.settlement_date} amt={e.amount_home} link={e.linked_event_id}")
        lines.append("-- DEBIT events within window or reserved/scheduled:")
        start, end = F._window(ctx, 90)
        for e in ctx.events:
            if e.direction != "debit":
                continue
            w = e.settlement_date or e.event_date
            if w and start <= w <= end:
                lines.append(f"{e.event_id} {e.tag.value} {e.status} {e.event_type} {e.category} "
                             f"{e.flexibility} ev={e.event_date} st={e.settlement_date} amt={e.amount_home}")
        lines.append("-- our projected FLOWS (nonzero, first 45 days):")
        _, _, flows = F.forecast_balance(ctx, 90)
        for day in sorted(flows):
            if day <= req.request_date + __import__("datetime").timedelta(days=45):
                lines.append(f"  {day} {flows[day]:+.2f}")
        series, minb, _ = F.forecast_balance(ctx, 90)
        lines.append(f"min_balance_90d={minb:.2f}")
        lines.append("-- messages:")
        for m in ctx.user_messages:
            lines.append(str(m))
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
