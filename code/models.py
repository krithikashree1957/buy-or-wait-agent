"""Data models for the Buy or Wait? decision output.

Output.csv contract (exact column order):

    request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,
    payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
"""

from __future__ import annotations

from dataclasses import dataclass
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
