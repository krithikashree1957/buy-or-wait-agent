"""Load the participant-facing dataset files from dataset/.

Every loader returns rows as plain string dicts (csv.DictReader output);
parsing/validation happens downstream (models.py, forecasting.py).
"""

from __future__ import annotations

import csv
from pathlib import Path

# code/ingest.py -> repo root is two levels up
REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "dataset"


def load_csv(filename: str) -> list[dict[str, str]]:
    """Read one dataset CSV and return its rows as raw string dicts."""
    with (DATASET_DIR / filename).open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_requests() -> list[dict[str, str]]:
    """dataset/requests.csv - the 250 evaluation requests to answer."""
    return load_csv("requests.csv")


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
