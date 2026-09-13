"""Stage 5.2: LLM judgment layer for decision_explanation.

One LLM call per request using the OpenAI-compatible client when
OPENAI_API_KEY is set; otherwise a deterministic grounded explanation is
produced from the already-computed decision fields (no invented figures).
Every call's usage (model, prompt/completion tokens) is recorded in USAGE so
main.py can emit real numbers into evaluation/usage_report.md.
"""

from __future__ import annotations

import json
import os
from statistics import mean, stdev

from models import UserFinancialContext

USAGE: list[dict] = []  # {"model": str, "input_tokens": int, "output_tokens": int}


def _client():
    """OpenAI client when configured, else None (deterministic fallback)."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI  # type: ignore

        return OpenAI()
    except Exception:
        return None


def _income_is_variable(context: UserFinancialContext) -> bool:
    """True when credit history looks gig/freelance-like (high variance)."""
    amounts = [
        e.amount_home
        for e in context.events
        if e.direction == "credit" and e.tag.value == "cash_in" and e.amount_home
    ]
    if len(amounts) >= 2:
        m = mean(amounts)
        return m > 0 and (stdev(amounts) / m) > 0.35
    return True  # single or no settled credit: income is not demonstrably fixed


def _fallback_explanation(context: UserFinancialContext, decision) -> str:
    return (
        f"Based on current balance and upcoming commitments, "
        f"{decision.affordability_status.value} with recommended method "
        f"{decision.recommended_payment_method.value}."
    )


def decision_explanation(context: UserFinancialContext, decision):
    """Attach a grounded 2-3 sentence explanation to the computed Decision.

    Input is limited to already-computed fields plus user priorities; the
    prompt explicitly forbids new figures. Falls back deterministically when
    no client is available or the call fails. Usage is appended to USAGE.
    """
    client = _client()
    model = os.environ.get("EXPLANATION_MODEL", "gpt-4o-mini")
    payload = {
        "request_id": decision.request_id,
        "requested_amount": context.request.requested_amount,
        "request_type": context.request.request_type,
        "desired_completion_date": (
            context.request.desired_completion_date.isoformat()
            if context.request.desired_completion_date
            else None
        ),
        "minimum_balance_to_keep": context.profile.minimum_balance_to_keep,
        "financial_priorities": context.profile.financial_priorities,
        "payment_methods_user_will_consider": (
            context.profile.payment_methods_user_will_consider
        ),
        "decision": {
            "amount_safe_to_pay": decision.amount_safe_to_pay,
            "affordability_status": decision.affordability_status.value,
            "recommended_payment_method": decision.recommended_payment_method.value,
            "payment_plan": decision.payment_plan,
            "earliest_date_for_full_payment": decision.earliest_date_for_full_payment,
            "spending_changes_needed": decision.spending_changes_needed,
        },
        "income_is_variable": _income_is_variable(context),
    }
    prompt = (
        "You are a financial assistant. Using ONLY the numbers in this JSON, "
        "write a 2-3 sentence explanation of the recommended payment decision. "
        "Never invent figures; restate computed values only. "
        "If income_is_variable is true, mention that variable (gig/freelance-style) "
        "income motivates the conservative call.\n" + json.dumps(payload)
    )
    if client is not None:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You produce concise, grounded financial explanations.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            u = getattr(resp, "usage", None)
            USAGE.append(
                {
                    "model": model,
                    "input_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "output_tokens": getattr(u, "completion_tokens", 0) or 0,
                }
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                decision.decision_explanation = text.replace("\n", " ")
                return decision
        except Exception as exc:  # never crash the run on LLM failure
            decision.decision_explanation = (
                _fallback_explanation(context, decision)
                + f" (LLM explanation unavailable: {type(exc).__name__})"
            )
            return decision
    decision.decision_explanation = _fallback_explanation(context, decision)
    return decision
