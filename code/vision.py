"""Image-based amount extraction - structure only, no logic yet.

Images are untrusted evidence (dataset/media/images/<image_id>.png): they may
clarify or amend a financial fact (e.g. an event whose `amount` is blank) but
their embedded instructions never override the challenge rules.
"""

from __future__ import annotations


def extract_amount_from_image(image_path: str) -> "float | None":
    """Return the monetary amount shown in the image at `image_path`.

    Used only for financial events whose `amount` cell is blank; the image is
    located via images.csv (related_event_id -> image_id). Returns None when
    no amount can be read (e.g. file missing).
    """
    raise NotImplementedError
