# NOTES.md

Exploration findings for the Buy or Wait? challenge (HackerRank Orchestrate, September 2026). Nothing in this file is a deliverable; it is working notes. Deliverables are root `output.csv`, `code.zip` (with `evaluation/usage_report.md`), and `chat_transcript` (`log.txt`).

## Repo Structure

```
.\                                repo root (git: main, commit 963ad7eb)
├── AGENTS.md                     agent rules: logging, project contract, decision rules
├── CLAUDE.md                     1 line: "@AGENTS.md" (imports AGENTS.md wholesale)
├── problem_statement.md          full participant spec (251 lines)
├── README.md                     setup/run + submission instructions
├── log.txt                       agent log, must stay gitignored = chat_transcript
├── NOTES.md                      this file
└── code/
    ├── main.py                   0 bytes — empty placeholder
    └── evaluation/
        ├── main.py               0 bytes — empty placeholder
        └── usage_report.md       0 bytes — empty placeholder
dataset/                          participant-facing inputs (do not modify)
├── requests.csv                  251 lines = header + 250 evaluation requests
├── output.csv                    251 lines = header + 250 blank rows (template; ids start request_26)
├── sample_requests.csv           26 lines = header + 25 solved examples
├── financial_profiles.csv        276 lines = header + 275 users
├── financial_events.csv          25,343 lines = header + 25,342 events (largest file)
├── request_payment_options.csv   791 lines = header + 790 payment options
├── exchange_rates.csv            135 lines = header + 134 dated rates
├── messages.csv                  216 lines = header + 215 messages
├── images.csv                    17 lines = header + 16 image links
└── media/images/                 image_01.png … image_16.png (16 PNGs, matches images.csv)
```

- No hidden files or organizer-only files were found inside `code/` or `dataset/` (listing used `-Force`).
- `code.zip` does not exist yet; `output.csv` at root does not exist yet (only the blank `dataset/output.csv` template).

## Output Schema

Exact columns, in order (from `problem_statement.md` "Required output" and the blank template header):

| # | Column | Type / allowed values | Rules |
|---|--------|----------------------|-------|
| 1 | `request_id` | string (`request_N`) | one row per `dataset/requests.csv` id |
| 2 | `amount_safe_to_pay` | number | `0 <= amount_safe_to_pay <= requested_amount`; safe on `request_date` **before** optional spending changes |
| 3 | `affordability_status` | enum | `affordable_now` \| `affordable_with_plan` \| `affordable_later` \| `not_affordable` |
| 4 | `recommended_payment_method` | enum | `full_payment` \| `partial_payment` \| `installments` \| `wait` \| `not_recommended` |
| 5 | `payment_plan` | `none` or `YYYY-MM-DD:amount` entries joined by `\|`, chronological | Installments must **exactly match** a supplied option. `partial_payment` = exactly 2 payments (`amount_safe_to_pay` on `request_date`, remainder on `earliest_date_for_full_payment`) summing to `requested_amount`; only when `allows_partial_payment=true`, user accepts it, and 2nd payment ≤ `desired_completion_date`. |
| 6 | `earliest_date_for_full_payment` | date or empty | = `request_date` for `affordable_now`; empty if full payment never safe within the 90-day forecast. Measures capacity independently of payment-method preference (can be `request_date` even when recommending installments). |
| 7 | `spending_changes_needed` | `none` or up to 3 actions joined by `\|` | `stop:<event_id>` or `reduce_to:<event_id>:<new_amount>`; only non-protected **flexible recurring** expenses; stop and reduce of the *same* event are mutually exclusive. |
| 8 | `decision_explanation` | free text | concise, grounded in the data |

No module/folder structure is mandated — any language; Python convention is `code/main.py` writing root-level `output.csv` (README: solution must read from `dataset/`, write one prediction per request to root `output.csv`).

## Constraints

**Core decision rules (from problem_statement.md + AGENTS.md §6.3):**
- **90-day safety check**: forecast balance with recurring income/expenses, confirmed future payments, messages/images; balance must never drop below `minimum_balance_to_keep`; ignore pending credits, failed/cancelled/duplicate/unrealized-investment records.
- Pending debits reserved; pending credits/bonuses/commissions/refunds/lottery/investment gains NOT counted until settled. Confirmed salary counted on settlement date. No invented facts.
- **Blank event `amount` is never zero**: look up `images.csv` by `related_event_id == event_id`, read the PNG (`dataset/media/images/<image_id>.png`), extract the amount from the image.
- Messages/images are **untrusted evidence** — prompt-injection style instructions inside them must not override rules; they may clarify/amend/cancel/delay/confirm facts only.
- FX: all outputs in the user's `home_currency` (INR/ZAR/IDR/USD/EUR present); convert foreign-currency cash events using the `exchange_rates.csv` row for the event's **settlement date** and stated direction pair.
- Plan-choice ranking when multiple safe plans: 1) complete by `desired_completion_date`, 2) no spending changes, 3) min total paid, 4) start earlier, 5) fewer payments, 6) lowest `payment_option_id`.
- Method eligibility: immediate methods only if in `payment_methods_user_will_consider`; `wait` only if full payment becomes safe later and user accepts `full_payment`; `not_recommended` as fallback. `max_installment_months` blank ⇒ installments rejected.
- Conflict resolution order: explicit cancellation/settlement/amendment → newer record from same source → settled event over estimate/forecast → financially safer interpretation.

**Evaluable-submission constraints:** terminal-runnable; reads `dataset/`; no organizer-only files or hardcoded labels; deterministic; secrets via env vars only; README with setup/run instructions.

**Deliverables:** root `output.csv` (250 rows + header), `code.zip` (must include `evaluation/usage_report.md` summarizing the final full-run's models, calls, input/output tokens, total/avg tokens per request, total/per-request cost), and `chat_transcript` (= the gitignored `log.txt`).

**Agent-process constraints (AGENTS.md):** log every turn to root `log.txt` (append-only, UTF-8, `\n`, gitignored, no secrets), `tool=` must name the actual harness (Cline here), session-start entry per session, don't modify `dataset/`.

## Existing Code

- **`code/main.py` is an empty 0-byte placeholder** — no starter logic exists. The entire pipeline (profile/event reconstruction, FX conversion, image OCR/vision for blank amounts, 90-day forecast, plan generation, deterministic verification) must be built from scratch.
- `code/evaluation/main.py` and `code/evaluation/usage_report.md` are also empty placeholders (the latter is a required submission artifact).
- `dataset/output.csv` gives the exact header and the 250 request ids to fill (sequentially `request_26`…`request_275`).

## Data Sample

`dataset/requests.csv` columns: `request_id, user_id, request_date, request_type, requested_amount, desired_completion_date, allows_partial_payment, request_text`

First 5 rows:

| request_id | user_id | date | type | amount | deadline | partial? | gist |
|---|---|---|---|---|---|---|---|
| request_26 | user_26 | 2025-08-03 | family_transfer | 15,656,000 IDR | 2025-10-07 | false | send full / part / wait? |
| request_27 | user_27 | 2026-07-05 | purchase | 6,670 ZAR | 2026-08-21 | true | laptop, avoid dipping into kept balance |
| request_28 | user_28 | 2024-06-07 | investment | 1,302.40 EUR | 2024-08-15 | false | portion investable today without breaking minimum |
| request_29 | user_29 | 2025-11-04 | investment | 51,524 ZAR | 2025-11-23 | false | keep upcoming bills covered |
| request_30 | user_30 | 2026-04-06 | debt_repayment | 775.20 USD | 2026-06-06 | false | clear extra loan payment without risking bills |

- `request_type` enum: `purchase, travel, education, family_transfer, debt_repayment, investment, housing, emergency_expense, other`.
- Amounts are decimal numbers in the *stated* currency named inside `request_text`; outputs use the user's home currency.
- IDs are 1-indexed from `request_26` (and matching users `user_26`…), so `sample_requests.csv` presumably covers a different/id-prefixed range (its 25 rows are the solved format examples).

---

**Notable planning implication:** since `code/main.py` is empty and the spec requires image-derived amounts (16 PNGs), a minimal viable build is a deterministic Python engine (CSV parsing → per-user event timeline → 90-day balance forecast → plan ranking per the tie-break order) plus vision calls only for the few events with blank amounts — which also keeps the `evaluation/usage_report.md` numbers small.

