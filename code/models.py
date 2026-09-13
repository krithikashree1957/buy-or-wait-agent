"""Data models for the Buy or Wait? decision output.

Output.csv contract (exact column order):

    request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,
    payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import ClassVar


class AffordabilityStatus(str, Enum):
    AFFORDABLE_NOW = "affordable_now"
    AFFORDABLE_WITH_PLAN = "affordable_with_plan"
    AFFORDABLE_LATER = "affordable_later"
    NOT_AFFORDABLE = "not_affordable"


class PaymentMethod(str, Enum):
    FULL_PAYMENT = "full_payment"
    PARTIAL_PAYMENT = "partial_payment"
    INSTALLMENTS = "installments"
    WAIT = "wait"
    NOT_RECOMMENDED = "not_recommended"


@dataclass
class Decision:
    """One output.csv row, in exact schema order."""

    request_id: str = ""
    amount_safe_to_pay: str = "0"  # 0 <= value <= requested_amount
    affordability_status: AffordabilityStatus = AffordabilityStatus.NOT_AFFORDABLE
    recommended_payment_method: PaymentMethod = PaymentMethod.NOT_RECOMMENDED
    payment_plan: str = "none"  # "none" or chronological YYYY-MM-DD:amount|...
    earliest_date_for_full_payment: str = ""  # YYYY-MM-DD or empty
    spending_changes_needed: str = "none"  # "none" or stop:<id>/reduce_to:<id>:<amt>
    decision_explanation: str = ""

    HEADER: ClassVar[tuple[str, ...]] = (
        "request_id",
        "amount_safe_to_pay",
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
        "decision_explanation",
    )

    def to_row(self) -> list[str]:
        """Serialize to a CSV row in the exact schema order."""
        return [
            self.request_id,
            self.amount_safe_to_pay,
            self.affordability_status.value,
            self.recommended_payment_method.value,
            self.payment_plan,
            self.earliest_date_for_full_payment,
            self.spending_changes_needed,
            self.decision_explanation,
        ]


# ---------------------------------------------------------------------------
# Ingest-layer models (dataset-shaped)
# ---------------------------------------------------------------------------

class CashFlowTag(str, Enum):
    """How an event counts toward cash flow (exclusion rules in NOTES.md)."""

    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    PENDING_DEBIT_RESERVE = "pending_debit_reserve"
    SCHEDULED_DEBIT_OUTFLOW = "scheduled_debit_outflow"
    EXCLUDED_CANCELLED = "excluded_cancelled"
    EXCLUDED_DUPLICATE = "excluded_duplicate"
    EXCLUDED_FAILED = "excluded_failed"
    EXCLUDED_UNREALIZED = "excluded_unrealized"
    EXCLUDED_PENDING_CREDIT = "excluded_pending_credit"
    EXCLUDED_SCHEDULED_CREDIT = "excluded_scheduled_credit"
    EXCLUDED_NON_CASH = "excluded_non_cash"
    UNKNOWN_STATUS_REVIEW = "unknown_status_review"


@dataclass
class EventRecord:
    """One financial_events.csv row, parsed, tagged, and home-converted."""

    event_id: str
    user_id: str
    event_type: str
    category: str
    description: str
    direction: str
    status: str
    event_date: date | None
    settlement_date: date | None
    amount: float | None
    currency: str
    amount_home: float | None
    fx_note: str
    linked_event_id: str
    flexibility: str
    minimum_allowed_amount: float | None
    tag: CashFlowTag
    resolution: str
    notes: list[str] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class PaymentOptionRecord:
    """One request_payment_options.csv row (amounts in request/home currency)."""

    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float | None
    number_of_payments: int | None
    first_payment_date: date | None
    payment_frequency_days: int | None
    financing_fee: float
    total_payable_amount: float | None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class ProfileRecord:
    """One financial_profiles.csv row."""

    user_id: str
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: list[str]
    protected_categories: list[str]
    reducible_categories: list[str]
    stoppable_categories: list[str]
    payment_methods_user_will_consider: list[str]
    max_installment_months: int | None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class RequestRecord:
    """One requests.csv / sample_requests.csv row."""

    request_id: str
    user_id: str
    request_date: date | None
    request_type: str
    requested_amount: float
    desired_completion_date: date | None
    allows_partial_payment: bool
    request_text: str
    currency_codes_in_text: list[str]
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class UserFinancialContext:
    """Everything needed to decide one request, in the user's home currency."""

    request: RequestRecord
    profile: ProfileRecord
    events: list[EventRecord]  # included (cash counting / reserved outflows)
    excluded_records: list[EventRecord]  # dropped per exclusion rules, kept here
    exclusions: list[str]  # human-readable reason per excluded event
    payment_options: list[PaymentOptionRecord]
    user_messages: list[dict[str, str]]  # raw rows for the user
    request_messages: list[dict[str, str]]  # subset also linked to this request
    warnings: list[str]
    request_source: str = "requests.csv"
