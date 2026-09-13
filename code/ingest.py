"""Load the participant-facing dataset files and assemble per-request
UserFinancialContext objects.

Cash-state rules (NOTES.md / AGENTS.md 6.3):
- settled events count by direction (debit = outflow, credit = inflow)
- pending debits are reserved (committed outflow), pending credits are NOT
  counted until they settle (excluded, reason logged)
- scheduled debits count as future committed outflow; scheduled credits do not
- failed / cancelled / duplicate / unrealized (non-cash investment value)
  records are excluded with a logged reason
- foreign-currency amounts convert to the profile's home_currency using
  exchange_rates.csv matched by the event's settlement date (event_date
  fallback): stated direction pair first, then the inverse pair, then a
  deterministic same-date chain; unresolvable FX leaves amount_home None
  plus a warning (never silently zero)
- blank event amounts resolve via images.csv (related_event_id -> image_id ->
  dataset/media/images/<image_id>.png) through vision.py's
  extract_amount_from_image; the vision stub raises NotImplementedError, so
  the lookup is wired and recorded but the amount stays None with a warning
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Callable

from models import (
    CashFlowTag,
    EventRecord,
    PaymentOptionRecord,
    ProfileRecord,
    RequestRecord,
    UserFinancialContext,
)
from vision import extract_amount_from_image

# code/ingest.py -> repo root is two levels up
REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "media" / "images"

_CURRENCY_RE = re.compile(r"\b(IDR|ZAR|USD|EUR|INR)\b")


def load_csv(filename: str) -> list[dict[str, str]]:
    """Read one dataset CSV and return its rows as raw string dicts."""
    with (DATASET_DIR / filename).open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_requests() -> list[dict[str, str]]:
    """dataset/requests.csv - the 250 evaluation requests to answer."""
    return load_csv("requests.csv")


def load_sample_requests() -> list[dict[str, str]]:
    """dataset/sample_requests.csv - 25 solved examples (format reference)."""
    return load_csv("sample_requests.csv")


def load_financial_profiles() -> list[dict[str, str]]:
    """dataset/financial_profiles.csv - home currency, balances, priorities, preferences."""
    return load_csv("financial_profiles.csv")


def load_financial_events() -> list[dict[str, str]]:
    """dataset/financial_events.csv - historical/pending/scheduled/settled events."""
    return load_csv("financial_events.csv")


def load_request_payment_options() -> list[dict[str, str]]:
    """dataset/request_payment_options.csv - seller/provider payment options per request."""
    return load_csv("request_payment_options.csv")


def load_exchange_rates() -> list[dict[str, str]]:
    """dataset/exchange_rates.csv - fixed dated FX rates."""
    return load_csv("exchange_rates.csv")


def load_messages() -> list[dict[str, str]]:
    """dataset/messages.csv - untrusted message evidence."""
    return load_csv("messages.csv")


def load_images() -> list[dict[str, str]]:
    """dataset/images.csv - image links; files resolve to dataset/media/images/<image_id>.png."""
    return load_csv("images.csv")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def parse_date(text: str | None) -> date | None:
    """Parse an ISO yyyy-mm-dd cell; blank/unparseable -> None."""
    if not text or not text.strip():
        return None
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


def parse_amount(text: str | None) -> float | None:
    """Parse a decimal amount; blank -> None (never silently zero)."""
    if text is None:
        return None
    cleaned = text.replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_bool(text: str | None) -> bool:
    """Parse a true/false cell (blank -> False)."""
    return (text or "").strip().lower() == "true"


def split_multi(text: str | None) -> list[str]:
    """Split a |-separated multi-value cell into a clean list."""
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


# ---------------------------------------------------------------------------
# FX conversion (settlement-date matched)
# ---------------------------------------------------------------------------
class FxTable:
    """Dated FX rates with deterministic direct/inverse/chain conversion."""

    def __init__(self, rate_rows: list[dict[str, str]]) -> None:
        self._rates: dict[tuple[str, str, str], float] = {}
        for row in rate_rows:
            rate = parse_amount(row.get("rate"))
            if rate is None:
                continue
            self._rates[
                (
                    (row.get("from_currency") or "").strip().upper(),
                    (row.get("to_currency") or "").strip().upper(),
                    (row.get("rate_date") or "").strip(),
                )
            ] = rate

    def _edges(self, day: str) -> dict[tuple[str, str], float]:
        """All rate edges available on one date."""
        return {
            (src, dst): rate
            for (src, dst, on), rate in self._rates.items()
            if on == day
        }

    def convert(
        self, amount: float, from_cur: str, to_cur: str, on_day: str
    ) -> tuple[float | None, str]:
        """Convert amount from_cur -> to_cur using rows dated `on_day` only.

        Returns (converted_amount, explanation). converted_amount is None when
        no same-date path exists (never guessed from another date).
        """
        from_cur = from_cur.strip().upper()
        to_cur = to_cur.strip().upper()
        if from_cur == to_cur:
            return amount, "native"
        if not on_day:
            return None, f"no settlement date for FX {from_cur}->{to_cur}"
        edges = self._edges(on_day)
        direct = edges.get((from_cur, to_cur))
        if direct is not None:
            return amount * direct, f"{from_cur}->{to_cur} @ {on_day} rate {direct}"
        inverse = edges.get((to_cur, from_cur))
        if inverse:
            return (
                amount / inverse,
                f"inverse of {to_cur}->{from_cur} @ {on_day} rate {inverse}",
            )
        # Deterministic BFS over same-date edges (each usable in both
        # directions), neighbors visited in sorted order.
        queue: list[tuple[str, float, list[str]]] = [(from_cur, 1.0, [from_cur])]
        while queue:
            cur, factor, path = queue.pop(0)
            if cur == to_cur:
                return (
                    amount * factor,
                    f"chain {'->'.join(path)} @ {on_day} (factor {factor:.10g})",
                )
            if len(path) > 4:
                continue
            for src, dst in sorted(edges):
                rate = edges[(src, dst)]
                if src == cur and rate:
                    queue.append((dst, factor * rate, path + [dst]))
                elif dst == cur and rate:
                    queue.append((src, factor / rate, path + [src]))
        return None, f"no same-date rate path {from_cur}->{to_cur} on {on_day}"


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------
def build_profile(row: dict[str, str]) -> ProfileRecord:
    """Parse one financial_profiles.csv row."""
    months = parse_amount(row.get("max_installment_months"))
    return ProfileRecord(
        user_id=(row.get("user_id") or "").strip(),
        home_currency=(row.get("home_currency") or "").strip().upper(),
        current_available_balance=parse_amount(row.get("current_available_balance")) or 0.0,
        minimum_balance_to_keep=parse_amount(row.get("minimum_balance_to_keep")) or 0.0,
        financial_priorities=split_multi(row.get("financial_priorities")),
        protected_categories=split_multi(row.get("expense_categories_to_protect")),
        reducible_categories=split_multi(
            row.get("expense_categories_user_is_willing_to_reduce")
        ),
        stoppable_categories=split_multi(
            row.get("expense_categories_user_is_willing_to_stop")
        ),
        payment_methods_user_will_consider=split_multi(
            row.get("payment_methods_user_will_consider")
        ),
        max_installment_months=int(months) if months is not None else None,
        raw=row,
    )


def build_request(row: dict[str, str]) -> RequestRecord:
    """Parse one requests.csv / sample_requests.csv row."""
    text = row.get("request_text") or ""
    return RequestRecord(
        request_id=(row.get("request_id") or "").strip(),
        user_id=(row.get("user_id") or "").strip(),
        request_date=parse_date(row.get("request_date")),
        request_type=(row.get("request_type") or "").strip(),
        requested_amount=parse_amount(row.get("requested_amount")) or 0.0,
        desired_completion_date=parse_date(row.get("desired_completion_date")),
        allows_partial_payment=parse_bool(row.get("allows_partial_payment")),
        request_text=text,
        currency_codes_in_text=sorted(set(_CURRENCY_RE.findall(text))),
        raw=row,
    )


def build_payment_option(row: dict[str, str]) -> PaymentOptionRecord:
    """Parse one request_payment_options.csv row."""
    n_payments = parse_amount(row.get("number_of_payments"))
    frequency = parse_amount(row.get("payment_frequency_days"))
    return PaymentOptionRecord(
        payment_option_id=(row.get("payment_option_id") or "").strip(),
        request_id=(row.get("request_id") or "").strip(),
        payment_method=(row.get("payment_method") or "").strip(),
        payment_amount=parse_amount(row.get("payment_amount")),
        number_of_payments=int(n_payments) if n_payments is not None else None,
        first_payment_date=parse_date(row.get("first_payment_date")),
        payment_frequency_days=int(frequency) if frequency is not None else None,
        financing_fee=parse_amount(row.get("financing_fee")) or 0.0,
        total_payable_amount=parse_amount(row.get("total_payable_amount")),
        raw=row,
    )


def build_event(
    row: dict[str, str],
    home_currency: str,
    fx: FxTable,
    images_by_event: dict[str, dict[str, str]],
    extract_amount: Callable[[str], float | None],
) -> EventRecord:
    """Parse, cash-state-tag, and home-convert one financial_events.csv row."""
    event_id = (row.get("event_id") or "").strip()
    status = (row.get("status") or "").strip().lower()
    direction = (row.get("direction") or "").strip().lower()
    event_type = (row.get("event_type") or "").strip().lower()
    currency = (row.get("currency") or "").strip().upper()
    amount = parse_amount(row.get("amount"))
    settlement = parse_date(row.get("settlement_date")) or parse_date(
        row.get("event_date")
    )
    on_day = settlement.isoformat() if settlement else ""

    notes: list[str] = []
    resolution = ""
    fx_note = ""
    amount_home: float | None = None

    if amount is None:
        # Blank amount: resolve via images.csv -> vision stub (wired, not implemented).
        image_row = images_by_event.get(event_id)
        if image_row:
            image_id = (image_row.get("image_id") or "").strip()
            image_path = str(IMAGES_DIR / f"{image_id}.png")
            resolution = f"blank amount; image lookup {image_path}"
            try:
                extracted = extract_amount(image_path)
            except NotImplementedError:
                extracted = None
                resolution += " (vision stub not implemented)"
            except Exception as exc:  # vision may fail per-file
                extracted = None
                resolution += f" (vision error: {exc})"
            if extracted is not None:
                amount = float(extracted)
                resolution += f" -> amount {extracted}"
                notes.append(f"{event_id}: amount taken from image {image_path}")
            else:
                notes.append(
                    f"{event_id}: blank amount unresolved (image {image_path})"
                )
        else:
            resolution = "blank amount; no linked image"
            notes.append(f"{event_id}: blank amount and no linked image")

    if amount is not None:
        if currency == home_currency:
            amount_home = amount
            fx_note = "native"
        elif not currency:
            amount_home = amount
            fx_note = "no currency given, assumed home"
        else:
            amount_home, fx_note = fx.convert(amount, currency, home_currency, on_day)
            if amount_home is None:
                notes.append(f"{event_id}: FX unresolved ({fx_note})")

    if status in ("cancelled", "canceled"):
        tag = CashFlowTag.EXCLUDED_CANCELLED
    elif status == "duplicate":
        tag = CashFlowTag.EXCLUDED_DUPLICATE
    elif status == "failed":
        tag = CashFlowTag.EXCLUDED_FAILED
    elif status == "unrealized":
        tag = CashFlowTag.EXCLUDED_UNREALIZED
    elif "non_cash" in status or "non-cash" in status or "non_cash" in event_type:
        tag = CashFlowTag.EXCLUDED_NON_CASH
    elif status == "pending" and direction == "credit":
        tag = CashFlowTag.EXCLUDED_PENDING_CREDIT
    elif status == "pending" and direction == "debit":
        tag = CashFlowTag.PENDING_DEBIT_RESERVE
    elif status == "scheduled" and direction == "credit":
        tag = CashFlowTag.EXCLUDED_SCHEDULED_CREDIT
    elif status == "scheduled" and direction == "debit":
        tag = CashFlowTag.SCHEDULED_DEBIT_OUTFLOW
    elif status == "settled":
        tag = CashFlowTag.CASH_OUT if direction == "debit" else CashFlowTag.CASH_IN
    else:
        tag = CashFlowTag.UNKNOWN_STATUS_REVIEW
        notes.append(f"{event_id}: unknown status '{status}' flagged for review")

    return EventRecord(
        event_id=event_id,
        user_id=(row.get("user_id") or "").strip(),
        event_type=event_type,
        category=(row.get("category") or "").strip(),
        description=(row.get("description") or "").strip(),
        direction=direction,
        status=status,
        event_date=parse_date(row.get("event_date")),
        settlement_date=parse_date(row.get("settlement_date")),
        amount=amount,
        currency=currency,
        amount_home=amount_home,
        fx_note=fx_note,
        linked_event_id=(row.get("linked_event_id") or "").strip(),
        flexibility=(row.get("flexibility") or "").strip(),
        minimum_allowed_amount=parse_amount(row.get("minimum_allowed_amount")),
        tag=tag,
        resolution=resolution,
        notes=notes,
        raw=row,
    )


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------
def load_user_context(
    request_id: str,
    *,
    extract_amount: Callable[[str], float | None] = extract_amount_from_image,
) -> UserFinancialContext:
    """Assemble the full financial context for one request_id.

    Looks up the request row (requests.csv, falling back to
    sample_requests.csv), the user's profile and events, the request's payment
    options, and the user's messages (flagging request-linked ones). Every
    cash-relevant amount is converted to the profile's home currency.
    Excluded events are returned with reasons, never silently dropped.
    """
    requests_by_id = {r["request_id"]: r for r in load_requests()}
    raw_request = requests_by_id.get(request_id)
    source = "requests.csv"
    if raw_request is None:
        raw_request = {
            r["request_id"]: r for r in load_sample_requests()
        }.get(request_id)
        source = "sample_requests.csv"
    if raw_request is None:
        raise KeyError(
            f"request_id {request_id!r} not found in requests.csv or sample_requests.csv"
        )
    request = build_request(raw_request)

    profiles = {p.get("user_id", ""): p for p in load_financial_profiles()}
    profile_row = profiles.get(request.user_id)
    if profile_row is None:
        raise KeyError(f"profile for {request.user_id!r} not found")
    profile = build_profile(profile_row)

    fx = FxTable(load_exchange_rates())
    images_by_event = {
        (img.get("related_event_id") or "").strip(): img
        for img in load_images()
        if (img.get("related_event_id") or "").strip()
    }

    events: list[EventRecord] = []
    excluded_records: list[EventRecord] = []
    exclusions: list[str] = []
    warnings: list[str] = []
    for row in load_financial_events():
        if (row.get("user_id") or "").strip() != request.user_id:
            continue
        record = build_event(
            row, profile.home_currency, fx, images_by_event, extract_amount
        )
        warnings.extend(record.notes)
        if record.tag.value.startswith("excluded_"):
            excluded_records.append(record)
            exclusions.append(
                f"{record.event_id} (status={record.status or 'blank'}, "
                f"type={record.event_type}, dir={record.direction or 'blank'}): "
                f"{record.tag.value}"
            )
        else:
            events.append(record)

    options = [
        build_payment_option(o)
        for o in load_request_payment_options()
        if o.get("request_id", "").strip() == request.request_id
    ]

    user_messages = [
        m
        for m in load_messages()
        if (m.get("user_id") or "").strip() == request.user_id
    ]
    request_messages = [
        m
        for m in user_messages
        if (m.get("request_id") or "").strip() == request.request_id
    ]

    return UserFinancialContext(
        request=request,
        profile=profile,
        events=events,
        excluded_records=excluded_records,
        exclusions=exclusions,
        payment_options=options,
        user_messages=user_messages,
        request_messages=request_messages,
        warnings=sorted(set(warnings)),
        request_source=source,
    )
