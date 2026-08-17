"""
License service — Gumroad v2 verify, machine-bound + offline grace.

Architecture
-----------
verify_license_online(key, fingerprint)
    → Calls Gumroad API; returns (is_valid, message, metadata dict).

Cached-license validation (no Qt dependency — pure dict):
    validate_cached_activation(cache: dict | None, current_fingerprint: str)
    → (is_valid, reason) with offline-grace logic.

The dev-mock backdoor is guarded behind SCRIBE_ALLOW_DEV_MOCK=1 env var
so it is NEVER active in the PyInstaller-shipped binary without explicit
env-set.  Tests use @patch('requests.post') and do not need the mock.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import requests

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────
OFFLINE_GRACE_DAYS = 30
"""Maximum days since *last_verified* a cached license is accepted offline."""

GUMROAD_PRODUCT_ID = "eyiexi"
"""Gumroad product permalink (hardcoded per product)."""

DEFAULT_CHECK_URL = "https://api.gumroad.com/v2/licenses/verify"


def _build_fingerprint_hash(fingerprint: str) -> str:
    """Obfuscated hash of the machine fingerprint for storage + Gumroad custom field."""
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]


class LicenseService:
    """License verification & offline-validation service.

    Thread-safe (no mutable instance state beyond config at init).
    """

    def __init__(
        self,
        check_url: str = DEFAULT_CHECK_URL,
        product_id: str = GUMROAD_PRODUCT_ID,
    ):
        self.check_url = check_url
        self.product_id = product_id

    # ── Online verification ─────────────────────────────────────────

    def verify_license_online(
        self,
        license_key: str,
        machine_fingerprint: str = "",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Verify *license_key* against Gumroad, optionally binding *machine_fingerprint*.

        Returns (is_valid, message, metadata_dict).

        Metadata keys useful for caching:
            purchase_email, license_type, purchase_timestamp, gumroad_response (raw).
        """
        key_cleaned = license_key.strip()
        if not key_cleaned:
            return False, "License key cannot be empty.", {}

        # ── Dev mock (NEVER active in production without explicit env) ──
        if os.environ.get("SCRIBE_ALLOW_DEV_MOCK", "0") == "1":
            if key_cleaned.startswith("dev-valid-"):
                mock_meta = {
                    "license_type": "Lifetime Developer",
                    "customer_name": "Developer Test",
                    "expires_at": None,
                    "status": "ACTIVE",
                    "purchase_timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return True, "Mock activation successful!", mock_meta

        try:
            payload: Dict[str, Any] = {
                "product_id": self.product_id,
                "license_key": key_cleaned,
            }
            # Append machine fingerprint as an opaque custom field so Gumroad logs it.
            if machine_fingerprint:
                payload["fingerprint"] = _build_fingerprint_hash(machine_fingerprint)

            response = requests.post(
                self.check_url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )

            try:
                data = response.json()
            except ValueError:
                data = {}

            is_valid = data.get("success", False)

            if is_valid:
                purchase = data.get("purchase", {})
                metadata = {
                    "license_type": purchase.get("product_name", "Paid License"),
                    "customer_name": purchase.get("email", "Customer"),
                    "purchase_timestamp": purchase.get("sale_timestamp"),
                    "expires_at": purchase.get("subscription_cancelled_at"),
                    "status": "ACTIVE",
                    "gumroad_purchase": purchase,
                }
                return True, "License verified successfully!", metadata
            else:
                msg = data.get("message") or f"Invalid license (HTTP {response.status_code})."
                return False, msg, {}

        except requests.RequestException as exc:
            logger.error("License network error: %s", exc)
            return False, (
                "Network error: could not reach licensing server. "
                "Please check your internet connection."
            ), {}

    # ── Offline / cached-license validation ─────────────────────────

    @staticmethod
    def validate_cached_activation(
        cache: Dict[str, Any] | None,
        current_fingerprint: str,
        now: datetime | None = None,
    ) -> Tuple[bool, str]:
        """Validate a previously-activated license from local cache.

        *cache* — dict previously returned by :meth:`build_cache` (or ``None``).
        *current_fingerprint* — machine fingerprint at this moment.
        *now* — override for testing (defaults to UTC now).

        Returns (is_valid, reason).

        Logic
        -----
        1. No cache                       → INVALID (never activated).
        2. Fingerprint mismatch            → INVALID (different machine).
        3. Within OFFLINE_GRACE_DAYS       → VALID (offline allowed).
        4. Past grace, try online re-check → caller's responsibility.
           This method returns VALID with a warning so the app UI can
           decide whether to prompt re-activation or silently re-check.
        """
        if not cache:
            return False, "No cached activation found."

        # 1. Fingerprint binding check
        stored_fingerprint = cache.get("fingerprint", "")
        if not stored_fingerprint:
            return False, "License not bound to a machine (corrupt cache)."

        expected = _build_fingerprint_hash(current_fingerprint)
        if stored_fingerprint != expected:
            return False, "License is for a different machine."

        # 2. Timestamp / grace check
        last_verified_str = cache.get("last_verified", "")
        if not last_verified_str:
            return True, "License valid (no timestamp)."  # legacy cache

        try:
            last_verified = datetime.fromisoformat(last_verified_str)
        except (ValueError, TypeError):
            return True, "License valid (unparseable timestamp)."

        if now is None:
            now = datetime.now(timezone.utc)
        # Naive timestamps in cache → assume UTC
        if last_verified.tzinfo is None:
            last_verified = last_verified.replace(tzinfo=timezone.utc)

        elapsed = (now - last_verified).days
        if elapsed <= OFFLINE_GRACE_DAYS:
            return True, f"License valid (last verified {elapsed} day(s) ago)."
        else:
            # Past grace: still VALID (soft), but caller SHOULD re-verify online.
            return True, (
                f"License grace period expired ({elapsed} days since last check). "
                "A network re-check is recommended."
            )

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def build_cache(
        license_key: str,
        machine_fingerprint: str,
        online_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a cache dictionary from a successful online verification.

        Caller persists this wherever it likes (QSettings, JSON file, etc.).
        """
        return {
            "key_hash": hashlib.sha256(license_key.strip().encode("utf-8")).hexdigest()[:16],
            "fingerprint": _build_fingerprint_hash(machine_fingerprint),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_verified": datetime.now(timezone.utc).isoformat(),
            "customer_name": online_metadata.get("customer_name", ""),
            "license_type": online_metadata.get("license_type", ""),
            "status": "ACTIVE",
        }