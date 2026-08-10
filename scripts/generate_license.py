"""Mint a Scribe Dictation Pro license key after a payment comes in (Stripe or crypto).

Run after you see a payment notification, then email the printed key to the buyer.
Not called by the app itself — the app only verifies keys, it never generates them.

Usage:
    uv run python scripts/generate_license.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scribe_dictation.licensing import generate_license_key  # noqa: E402

if __name__ == "__main__":
    print(generate_license_key())
