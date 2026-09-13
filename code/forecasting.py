"""Deterministic 90-day balance forecasting and payment-plan selection.

Implements the NOTES.md contract (no LLM calls; pure deterministic code):
- forecast_balance: day-by-day projection from request_date over `days`,
  applying pending-debit reserves, scheduled debits, future-dated settled
  events, and monthly recurrence projected from settled history (income
  projects from repeated income events; outflows from repeated regular
  expenses/subscriptions). The balance must never drop below
  minimum_balance_to_keep in any recommended plan.
- amount_safe_to_pay: max payable on request_date keeping the whole window
  >= minimum_balance_to_keep (0 <= result <= requested_amount).
- evaluate_payment_options: simulate only options actually listed for the
  request (never invented); safe = every payment date inside the window and
  balance >= minimum_balance_to_keep on every day of the window.
- rank_plans: exact 6-step tie-break from NOTES.md: 1) completes by
  desired_completion_date, 2) no spending changes, 3) min total paid,
  4) starts earlier, 5) fewer payments, 6) lowest payment_option_id.
- earliest_date_for_full_payment: first window day where one full payment
  keeps the balance >= minimum_balance_to_keep through the window end
  (independent of method preferences).
- decide: maps the ranked outcome to the output enums and eligibility rules
  (method must be in payment_methods_user_will_consider; blank
  max_installment_months rejects installments; wait/not_recommended fallback).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import floor, log10
from statistics import median

from models import (
    AffordabilityStatus,
    Decision,
    EventRecord,
    PaymentMethod,
    UserFinancialContext,
)

WINDOW_DAYS = 90
MIN_GAP_DAYS = 20
MAX_GAP_DAYS = 40
MIN_OCCURRENCES_DEBIT = 2
MIN_OCCURRENCES_INCOME = 1  # salary projects even from one settled occurrence


def fmt_amount(value: float) -> str:
    """Format money like the solved samples: no separators, minimal decimals."""
    rounded = round(value + 0.0, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _window(context: UserFinancialContext, days: int) -> tuple[date, date]:
    """Inclusive forecast window [request_date, request_date + days - 1]."""
    start = context.request.request_date
    return start, start + timedelta(days=days - 1)


def _sig3(value: float) -> float:
    """Round to 3 significant digits (clusters similar recurring amounts)."""
    if value == 0:
        return 0.0
    magnitude = floor(log10(abs(value)))
    scale = 10.0 ** (magnitude - 2)
    return round(round(value / scale) * scale, 2)


def _explicit_flows(
    context: UserFinancialContext, window_start: date, window_end: date
) -> dict[date, float]:
    """One-time flows inside the window from explicitly dated events.

    pending debits are reserved at max(settlement, request_date) (day 0 when
    dated before the request); scheduled debits apply on their date; settled
    events dated inside the window apply on their settlement date.
    """
    flows: dict[date, float] = {}
    for e in context.events:
        when = e.settlement_date or e.event_date
        if when is None:
            continue
        if e.tag.value == "pending_debit_reserve":
            when = max(when, window_start)
        elif e.tag.value == "scheduled_debit_outflow":
            when = e.event_date or when
        if when < window_start or when > window_end:
            continue
        amount = e.amount_home or 0.0
        sign = 1.0 if e.direction == "credit" else -1.0
        flows[when] = flows.get(when, 0.0) + sign * amount
    return flows


def _recurring_groups(
    context: UserFinancialContext,
) -> tuple[dict[tuple[str, str, float], list[tuple[date, float]]], set]:
    """Historical settled occurrences clustered by (direction, category, sig3).

    Returns (clusters of occurrences dated before request_date, key set of
    groups that have explicit future-dated settled rows so they are not
    double-counted by projection).
    """
    start = context.request.request_date
    clusters: dict[tuple[str, str, float], list[tuple[date, float]]] = {}
    future: set[tuple[str, str, float]] = set()
    for e in context.events:
        if e.tag.value not in ("cash_in", "cash_out"):
            continue
        when = e.settlement_date or e.event_date
        if when is None or not e.amount_home:
            continue
        key = (e.direction, e.category, _sig3(e.amount_home))
        if when < start:
            clusters.setdefault(key, []).append((when, e.amount_home))
        else:
            future.add(key)
    return clusters, future


def _project_recurring(
    context: UserFinancialContext, window_start: date, window_end: date
) -> dict[date, float]:
    """Project regular recurrence from settled history into the window.

    A cluster projects when it has enough occurrences (>=2 for outflows,
    >=1 for income/salary) and a regular cadence (median gap in [20, 40]
    days); amounts repeat at the median amount, stepping by the median gap
    from the last historical occurrence. Irregular one-offs (refunds,
    investment sales) fail the cadence test and never project.
    """
    flows: dict[date, float] = {}
    clusters, has_future = _recurring_groups(context)
    for key, occurrences in clusters.items():
        direction, _category, _amount = key
        if key in has_future:
            continue  # explicit future rows exist; projection would double count
        min_n = MIN_OCCURRENCES_INCOME if direction == "credit" else MIN_OCCURRENCES_DEBIT
        occurrences.sort()
        if len(occurrences) < min_n:
            continue
        dates = [d for d, _ in occurrences]
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        if gaps:
            gap = int(round(median(gaps)))
            if not (MIN_GAP_DAYS <= gap <= MAX_GAP_DAYS):
                continue
        else:
            gap = 30  # single income occurrence: conservative monthly default
        amount = median([a for _, a in occurrences])
        sign = 1.0 if direction == "credit" else -1.0
        t = dates[-1]
        while True:
            t = t + timedelta(days=gap)
            if t > window_end:
                break
            if t >= window_start:
                flows[t] = flows.get(t, 0.0) + sign * amount
    return flows


# --- forecast primitives (defined below) ---
def forecast_balance(context: UserFinancialContext, days: int = WINDOW_DAYS):
    """Day-by-day projected balance over the window.

    Returns (series, min_balance, flows) where series is a list of
    (date, balance_after_that_day) for every day from request_date, and
    flows maps date -> net applied movement (explicit + recurring).
    """
    window_start, window_end = _window(context, days)
    flows = _explicit_flows(context, window_start, window_end)
    for day, value in _project_recurring(context, window_start, window_end).items():
        flows[day] = flows.get(day, 0.0) + value

    balance = context.profile.current_available_balance
    series: list[tuple[date, float]] = []
    min_balance = balance
    for i in range(days):
        day = window_start + timedelta(days=i)
        balance += flows.get(day, 0.0)
        series.append((day, balance))
        min_balance = min(min_balance, balance)
    return series, min_balance, flows


def amount_safe_to_pay(context: UserFinancialContext, days: int = WINDOW_DAYS) -> float:
    """Max payable on request_date keeping the whole window >= minimum_balance_to_keep."""
    series, _, _ = forecast_balance(context, days)
    headroom = min(b for _, b in series) - context.profile.minimum_balance_to_keep
    return max(0.0, min(context.request.requested_amount, headroom))


def earliest_date_for_full_payment(
    context: UserFinancialContext, days: int = WINDOW_DAYS
) -> date | None:
    """First window day where one full payment keeps balance >= floor through window end.

    Implemented with suffix minima: paying `requested_amount` on day d is
    safe iff min(balance on days >= d) - requested_amount >=
    minimum_balance_to_keep. Returns None when no such day exists in the
    window (earliest is then reported empty).
    """
    series, _, _ = forecast_balance(context, days)
    need = context.profile.minimum_balance_to_keep + context.request.requested_amount
    result: date | None = None
    suffix_min: float | None = None
    for day, balance in reversed(series):
        suffix_min = balance if suffix_min is None else min(suffix_min, balance)
        if suffix_min >= need:
            result = day  # keep scanning back to the earliest qualifying day
    return result


@dataclass
class Plan:
    """One candidate payment plan (option-based or method-level action)."""

    method: PaymentMethod
    payments: list  # [(date, amount)] chronological
    total: float
    start: date
    option_id: str
    uses_spending_changes: bool = False

    @property
    def last_date(self) -> date:
        return max(d for d, _ in self.payments)


def evaluate_payment_options(context: UserFinancialContext, days: int = WINDOW_DAYS):
    """Simulate each listed payment option; return the safe ones.

    Safe = every payment date inside the forecast window AND base-window
    balance minus cumulative option payments >= minimum_balance_to_keep on
    every day of the window. Options are never invented - only rows from
    request_payment_options.csv for this request are simulated.
    """
    window_start, window_end = _window(context, days)
    series, _, _ = forecast_balance(context, days)
    floor = context.profile.minimum_balance_to_keep
    safe = []
    for option in context.payment_options:
        n = option.number_of_payments or 1
        first = option.first_payment_date or window_start
        step = option.payment_frequency_days or 30
        pay_dates = [first + timedelta(days=step * i) for i in range(n)]
        if any(d < window_start or d > window_end for d in pay_dates):
            continue
        amount = option.payment_amount or 0.0
        by_day: dict[date, int] = {}
        for d in pay_dates:
            by_day[d] = by_day.get(d, 0) + 1
        cumulative = 0.0
        is_safe = True
        for day, base in series:
            cumulative += amount * by_day.get(day, 0)
            if base - cumulative < floor:
                is_safe = False
                break
        if is_safe:
            safe.append(
                {
                    "option": option,
                    "pay_dates": pay_dates,
                    "amount": amount,
                    "total": option.total_payable_amount
                    if option.total_payable_amount is not None
                    else amount * n,
                }
            )
    return safe


def rank_plans(candidates: list[Plan], context: UserFinancialContext) -> list[Plan]:
    """Rank candidate plans by the exact 6-step tie-break order from NOTES.md:
    1) completes by desired_completion_date, 2) no spending changes,
    3) min total paid, 4) starts earlier, 5) fewer payments,
    6) lowest payment_option_id.
    """
    deadline = context.request.desired_completion_date

    def key(plan: Plan):
        on_time = deadline is None or plan.last_date <= deadline
        return (
            0 if on_time else 1,
            1 if plan.uses_spending_changes else 0,
            round(plan.total, 2),
            plan.start,
            len(plan.payments),
            plan.option_id,
        )

    return sorted(candidates, key=key)


def _option_plan(safe: dict) -> Plan:
    option = safe["option"]
    return Plan(
        method=PaymentMethod(option.payment_method),
        payments=list(zip(safe["pay_dates"], [safe["amount"]] * len(safe["pay_dates"]))),
        total=safe["total"],
        start=safe["pay_dates"][0],
        option_id=option.payment_option_id,
    )


def spending_changes_needed(
    context: UserFinancialContext, safe_options, days: int = WINDOW_DAYS
) -> str:
    """Minimum set of permitted spending changes that makes a full payment safe.

    Returns "none" when a safe plan already covers the full requested amount
    without changes. Otherwise greedily builds up to 3 actions drawn only from
    the user's reducible_categories / stoppable_categories events that fall in
    the window (never protected categories, never one action per event twice).
    Each candidate change is simulated; the change giving the largest headroom
    gain is kept (ties: stop before reduce, then lowest event_id). Reduce
    floors at minimum_allowed_amount, else halves the amount.
    """
    import copy as _copy
    from dataclasses import replace as _replace

    profile = context.profile
    request = context.request
    deadline = request.desired_completion_date
    protected = set(profile.protected_categories or [])
    reducible = set(profile.reducible_categories or [])
    stoppable = set(profile.stoppable_categories or [])

    def feasible(evts) -> bool:
        probe = _copy.copy(context)
        probe.events = evts
        d_full = earliest_date_for_full_payment(probe, days)
        return d_full is not None and (deadline is None or d_full <= deadline)

    if feasible(context.events):
        return "none"

    # Flexible, in-window cash-out events eligible for change.
    window_start, window_end = _window(context, days)
    eligible: list[EventRecord] = []
    for e in context.events:
        if e.tag.value not in ("cash_out", "scheduled_debit_outflow", "pending_debit_reserve"):
            continue
        if e.category in protected or e.direction != "debit" or not e.amount_home:
            continue
        if not (e.category in reducible or e.category in stoppable):
            continue
        when = e.settlement_date or e.event_date
        if when is None or not (window_start <= when <= window_end):
            continue
        eligible.append(e)

    actions: list[str] = []
    changed: dict[str, EventRecord] = {}
    for _ in range(3):
        best = None  # (gain, kind_rank, event_id, action_str, new_events)
        for e in eligible:
            if e.event_id in changed:
                continue  # stop and reduce of the same event are mutually exclusive
            for kind in ("stop", "reduce"):
                if kind == "reduce" and e.category not in reducible:
                    continue
                if kind == "stop" and e.category not in stoppable:
                    continue
                if kind == "reduce":
                    floor_amt = e.minimum_allowed_amount
                    new_amt = floor_amt if floor_amt is not None else e.amount_home / 2.0
                    new_amt = min(new_amt, e.amount_home)
                    if new_amt >= e.amount_home:
                        continue
                probe_events = list(context.events)
                probe_events.remove(e)
                if kind == "stop":
                    new_e = _replace(e, amount_home=0.0)
                else:
                    new_e = _replace(e, amount_home=new_amt)
                probe_events.append(new_e)
                probe = _copy.copy(context)
                probe.events = probe_events
                d_full = earliest_date_for_full_payment(probe, days)
                head = None
                if d_full is not None and (deadline is None or d_full <= deadline):
                    series, _, _ = forecast_balance(probe, days)
                    head = min(b for _, b in series)
                gain = head if head is not None else float("-inf")
                key = (gain, 0 if kind == "stop" else 1, e.event_id)
                if best is None or key > best[0]:
                    action = (
                        f"stop:{e.event_id}"
                        if kind == "stop"
                        else f"reduce_to:{e.event_id}:{fmt_amount(new_amt)}"
                    )
                    best = (key, action, new_e)
        if best is None or best[0][0] == float("-inf"):
            break
        _, action, new_e = best
        actions.append(action)
        changed[new_e.event_id] = new_e
        # Re-evaluate feasibility with accumulated changes.
        evts = [changed.get(x.event_id, x) for x in context.events]
        if feasible(evts):
            break

    if not feasible([changed.get(x.event_id, x) for x in context.events]):
        return "none"  # even maxed changes cannot make it safe; don't recommend them
    return "|".join(actions) if actions else "none"


def decide(context: UserFinancialContext, days: int = WINDOW_DAYS) -> Decision:
    """Produce the schema-valid Decision for one request's context.

    Eligibility rules: the recommended method must be in
    payment_methods_user_will_consider; blank max_installment_months rejects
    installments; partial payments require allows_partial_payment and a safe
    second payment by desired_completion_date; wait requires full_payment in
    the considered methods and a safe full-payment date within the window.
    """
    profile = context.profile
    request = context.request
    methods = [m.strip().lower() for m in profile.payment_methods_user_will_consider]
    requested = request.requested_amount
    safe_max = amount_safe_to_pay(context, days)
    d_full = earliest_date_for_full_payment(context, days)
    deadline = request.desired_completion_date
    window_start = request.request_date

    candidates: list[Plan] = []
    if "full_payment" in methods and requested <= safe_max + 1e-9:
        candidates.append(
            Plan(
                method=PaymentMethod.FULL_PAYMENT,
                payments=[(window_start, requested)],
                total=requested,
                start=window_start,
                option_id="full_now",
            )
        )

    for safe in evaluate_payment_options(context, days):
        option = safe["option"]
        method = option.payment_method.strip().lower()
        if method not in methods:
            continue
        if method == "installments":
            if profile.max_installment_months is None:
                continue  # blank max_installment_months rejects installments
            if (option.number_of_payments or 1) > profile.max_installment_months:
                continue
        candidates.append(_option_plan(safe))

    if (
        request.allows_partial_payment
        and "partial_payment" in methods
        and 0.0 < safe_max < requested
        and d_full is not None
        and (deadline is None or d_full <= deadline)
    ):
        candidates.append(
            Plan(
                method=PaymentMethod.PARTIAL_PAYMENT,
                payments=[(window_start, safe_max), (d_full, requested - safe_max)],
                total=requested,
                start=window_start,
                option_id="partial",
            )
        )

    if (
        d_full is not None
        and d_full > window_start
        and (deadline is None or d_full <= deadline)
        and "full_payment" in methods
    ):
        candidates.append(
            Plan(
                method=PaymentMethod.WAIT,
                payments=[(d_full, requested)],
                total=requested,
                start=d_full,
                option_id="wait",
            )
        )

    ranked = rank_plans(candidates, context)

    if ranked:
        best = ranked[0]
        plan_str = "|".join(f"{d.isoformat()}:{fmt_amount(a)}" for d, a in best.payments)
        if best.option_id == "full_now":
            status = AffordabilityStatus.AFFORDABLE_NOW
        elif best.method is PaymentMethod.WAIT:
            status = AffordabilityStatus.AFFORDABLE_LATER
        else:
            status = AffordabilityStatus.AFFORDABLE_WITH_PLAN
        method = best.method
        changes = "none"
    else:
        # No plan without changes: try permitted spending changes (Stage 5.1).
        plan_str = "none"
        method = PaymentMethod.NOT_RECOMMENDED
        if d_full is not None and (deadline is None or d_full <= deadline):
            status = AffordabilityStatus.AFFORDABLE_LATER  # capacity exists; no eligible plan
        else:
            status = AffordabilityStatus.NOT_AFFORDABLE
        changes = spending_changes_needed(context, [], days)
        if changes != "none":
            probe = context
            probe_events = list(context.events)
            for action in changes.split("|"):
                eid = action.split(":", 1)[1]
                for e in context.events:
                    if e.event_id == eid:
                        if action.startswith("stop:"):
                            new_e = EventRecord(**{**e.__dict__, "amount_home": 0.0})
                        else:
                            new_amt = float(action.rsplit(":", 1)[1])
                            new_e = EventRecord(**{**e.__dict__, "amount_home": new_amt})
                        probe_events[probe_events.index(e)] = new_e
                        break
            probe = context
            probe.events = probe_events
            d_full_changed = earliest_date_for_full_payment(probe, days)
            probe.events = context.events  # restore original context
            if d_full_changed is not None and (deadline is None or d_full_changed <= deadline):
                status = AffordabilityStatus.AFFORDABLE_WITH_PLAN
                plan_str = f"{d_full_changed.isoformat()}:{fmt_amount(requested)}"
                if "full_payment" in methods:
                    method = PaymentMethod.FULL_PAYMENT
                elif "wait" in methods:
                    method = PaymentMethod.WAIT
                d_full = d_full_changed

    earliest = d_full.isoformat() if d_full is not None else ""
    return Decision(
        request_id=request.request_id,
        amount_safe_to_pay=fmt_amount(safe_max),
        affordability_status=status,
        recommended_payment_method=method,
        payment_plan=plan_str,
        earliest_date_for_full_payment=earliest,
        spending_changes_needed=changes,
        decision_explanation="deterministic decision (explanation pending)",
    )
