"""90-day balance forecasting and plan ranking - structure only, no logic yet.

Planned behaviour (problem_statement.md / NOTES.md):
- forecast_balance: project available balance day by day over the forecast
  period, counting only cash-state events (settled/pending/scheduled/
  unrealized treated per their cash state), reserving pending debits, giving
  no credit to pending credits/bonuses/commissions/refunds/investment gains,
  converting foreign-currency events with the rate for the event's settlement
  date, and never dropping below minimum_balance_to_keep.
- rank_plans: order candidate plans by 1) completes by desired_completion_date,
  2) no spending changes, 3) lowest total paid, 4) earliest start,
  5) fewest payments, 6) lowest payment_option_id.
"""

from __future__ import annotations

from typing import Any, Callable

from models import Decision


def forecast_balance(
    profile: dict[str, str],
    events: list[dict[str, str]],
    exchange_rates: list[dict[str, str]],
    horizon_days: int = 90,
) -> Any:
    """Project the user's day-by-day available balance over `horizon_days`.

    Must respect cash-state filtering, pending-debit reservation, no credit
    for unsettled income, dated FX conversion, and minimum_balance_to_keep.
    """
    raise NotImplementedError


def rank_plans(
    request: dict[str, str],
    profile: dict[str, str],
    options: list[dict[str, str]],
    forecast: Any,
) -> list[Any]:
    """Return candidate payment plans ranked by the contract's tie-break order.

    Order: 1) completes by desired_completion_date, 2) no spending changes,
    3) minimal total paid, 4) earliest start, 5) fewest payments,
    6) lowest payment_option_id.
    """
    raise NotImplementedError


def decide(
    request: dict[str, str],
    profile: dict[str, str],
    events: list[dict[str, str]],
    options: list[dict[str, str]],
    exchange_rates: list[dict[str, str]],
    messages: list[dict[str, str]],
    images: list[dict[str, str]],
    extract_amount: Callable[[str], "float | None"],
) -> Decision:
    """Produce the final Decision for one request.

    Orchestrates evidence assembly (including blank-amount resolution via
    `extract_amount` on image paths), forecast_balance, rank_plans, and
    method-eligibility filtering into one schema-valid Decision.
    """
    raise NotImplementedError
