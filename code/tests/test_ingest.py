"""Manual sanity check for ingest.load_user_context.

Builds contexts for the first solved samples and prints readable summaries,
plus a global vocabulary scan of financial_events.csv statuses/directions so
the cash-state tagging rules can be checked against real values.

Run:  python code/tests/test_ingest.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import (  # noqa: E402
    load_financial_events,
    load_sample_requests,
    load_user_context,
)


def fmt_amount(value: object) -> str:
    return f"{value:,.2f}" if isinstance(value, (int, float)) else "None"


def summarize_context(ctx: object) -> str:
    req, prof = ctx.request, ctx.profile
    lines = []
    lines.append(
        f"=== {req.request_id} / {req.user_id} ({req.request_type}) "
        f"[from {ctx.request_source}] ==="
    )
    lines.append(
        f"profile: home={prof.home_currency} "
        f"balance={fmt_amount(prof.current_available_balance)} "
        f"min_keep={fmt_amount(prof.minimum_balance_to_keep)} "
        f"methods={prof.payment_methods_user_will_consider} "
        f"max_inst={prof.max_installment_months}"
    )
    lines.append(
        f"  priorities={prof.financial_priorities} "
        f"protected={prof.protected_categories}"
    )
    lines.append(
        f"  reducible={prof.reducible_categories} "
        f"stoppable={prof.stoppable_categories}"
    )
    lines.append(
        f"request: date={req.request_date} amount={fmt_amount(req.requested_amount)} "
        f"deadline={req.desired_completion_date} "
        f"partial={req.allows_partial_payment} "
        f"currencies_in_text={req.currency_codes_in_text}"
    )

    by_tag = Counter(e.tag.value for e in ctx.events)
    lines.append(
        f"events: {len(ctx.events)} included, "
        f"{len(ctx.excluded_records)} excluded"
    )
    for tag, count in sorted(by_tag.items()):
        subset = [e for e in ctx.events if e.tag.value == tag]
        inflow = sum(e.amount_home or 0 for e in subset if e.direction == "credit")
        outflow = sum(e.amount_home or 0 for e in subset if e.direction == "debit")
        lines.append(
            f"  {tag}: n={count} inflow={fmt_amount(inflow)} "
            f"outflow={fmt_amount(outflow)}"
        )
        for e in subset[:3]:
            lines.append(
                f"    e.g. {e.event_id} {e.event_date} {e.category} {e.direction} "
                f"{e.currency} {fmt_amount(e.amount)} -> home {fmt_amount(e.amount_home)}"
            )

    converted = [
        e
        for e in ctx.events
        if e.fx_note and e.fx_note not in ("native", "no currency given, assumed home")
    ]
    lines.append(f"fx conversions: {len(converted)}")
    for e in converted[:5]:
        lines.append(
            f"  {e.event_id}: {e.currency} {fmt_amount(e.amount)} -> "
            f"{fmt_amount(e.amount_home)} ({e.fx_note})"
        )

    unresolved = [e for e in ctx.events if e.amount_home is None]
    lines.append(f"unresolved amounts: {len(unresolved)}")
    for e in unresolved[:5]:
        lines.append(f"  {e.event_id}: {e.resolution} | notes={e.notes}")

    lines.append(f"exclusions ({len(ctx.exclusions)}):")
    for reason in ctx.exclusions[:8]:
        lines.append(f"  {reason}")

    lines.append(f"payment options ({len(ctx.payment_options)}):")
    for o in ctx.payment_options:
        lines.append(
            f"  {o.payment_option_id}: {o.payment_method} "
            f"amount={fmt_amount(o.payment_amount)} x{o.number_of_payments} "
            f"first={o.first_payment_date} freq_days={o.payment_frequency_days} "
            f"fee={fmt_amount(o.financing_fee)} total={fmt_amount(o.total_payable_amount)}"
        )

    sources = sorted({(m.get("source_type") or "") for m in ctx.user_messages})
    lines.append(
        f"messages: {len(ctx.user_messages)} for user, "
        f"{len(ctx.request_messages)} linked to request (sources={sources})"
    )
    for m in ctx.request_messages[:3]:
        text = (m.get("message_text") or "")[:80].replace("\n", " ")
        lines.append(f"  {m.get('message_id')} [{m.get('source_type')}] {text}...")

    if ctx.warnings:
        lines.append(f"warnings ({len(ctx.warnings)}):")
        for w in ctx.warnings[:8]:
            lines.append(f"  {w}")
    return "\n".join(lines)


def scan_dataset() -> str:
    """Distinct status/event_type/flexibility values + blank-amount count."""
    rows = load_financial_events()
    statuses = Counter((r.get("status") or "").strip() for r in rows)
    etypes = Counter((r.get("event_type") or "").strip() for r in rows)
    flexibility = Counter((r.get("flexibility") or "").strip() for r in rows)
    blank = sum(1 for r in rows if not (r.get("amount") or "").strip())
    lines = ["", "--- dataset scan (financial_events.csv, all rows) ---"]
    lines.append(f"rows={len(rows)} blank_amount={blank}")
    lines.append(f"statuses: {dict(sorted(statuses.items()))}")
    lines.append(f"event_types: {dict(sorted(etypes.items()))}")
    lines.append(f"flexibility: {dict(sorted(flexibility.items()))}")
    return "\n".join(lines)


def main() -> None:
    sample_ids = [r["request_id"] for r in load_sample_requests()[:3]]
    print(f"building contexts for sample requests: {sample_ids}\n")
    for request_id in sample_ids:
        print(summarize_context(load_user_context(request_id)))
        print()
    print(scan_dataset())


if __name__ == "__main__":
    main()
