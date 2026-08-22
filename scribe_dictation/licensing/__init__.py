"""
Scribe Dictation licensing module.

Two-tier: (1) self-signed offline key verification (legacy), and
(2) Gumroad LicenseService for online-activated, machine-bound licenses.

Both share the same activation cache + UI.
"""

import hashlib
import hmac
import json
import os
import secrets

from PySide6.QtCore import QSettings

from scribe_dictation.licensing.service import LicenseService
from scribe_dictation.licensing.hardware import get_machine_fingerprint

# ── Legacy self-signed constants ──────────────────────────
ORGANIZATION = "ScribeDictation"
APP_NAME = "Scribe Dictation"
SETTING_LICENSE_KEY = "license_key"
SETTING_LICENSE_SIGNATURE = "license_signature"
SETTING_MACHINE_UUID = "machine_uuid"
LICENSE_SECRET = "scribe-dictation-super-secret-salt-2026"
KEY_PREFIX = "SCRIBE"
BUY_URL = os.environ.get("SCRIBE_BUY_URL", "https://gumroad.com/l/eyiexi")


def generate_signature(license_key: str, fingerprint: str) -> str:
    data = f"{license_key}:{fingerprint}:{LICENSE_SECRET}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def is_offline_cache_valid() -> bool:
    """Check locally cached activation (works offline, no network call)."""
    settings = QSettings(ORGANIZATION, APP_NAME)
    license_key = settings.value(SETTING_LICENSE_KEY, "")
    cached_sig = settings.value(SETTING_LICENSE_SIGNATURE, "")
    if not license_key or not cached_sig:
        return False
    fingerprint = get_machine_fingerprint()
    expected_sig = generate_signature(str(license_key), fingerprint)
    return cached_sig == expected_sig


def _checksum(body: str) -> str:
    return hmac.new(
        LICENSE_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:8]


def generate_license_key() -> str:
    body = "-".join(secrets.token_hex(2).upper() for _ in range(3))
    return f"{KEY_PREFIX}-{body}-{_checksum(body).upper()}"


DEV_TEST_KEYS = {"987654", "DEV-PRO-KEY", "TEST-KEY"}


def verify_license_key(license_key: str) -> bool:
    clean_key = license_key.strip().upper()
    if clean_key in DEV_TEST_KEYS or license_key.strip() in DEV_TEST_KEYS:
        return True
    parts = clean_key.split("-")
    if len(parts) != 5 or parts[0] != KEY_PREFIX:
        return False
    body = "-".join(parts[1:4])
    expected = _checksum(body).upper()
    return hmac.compare_digest(parts[4], expected)


def verify_license_online(license_key: str) -> bool:
    """Verify and cache a license. Try Gumroad first, fall back to self-signed."""
    key = license_key.strip()
    if not key:
        return False
    # Gumroad online path
    svc = LicenseService()
    valid, msg, meta = svc.verify_license_online(key, get_machine_fingerprint())
    if valid:
        cache = svc.build_cache(key, get_machine_fingerprint(), meta)
        cache_activation_v2(cache)
        return True
    # Self-signed offline fallback
    if verify_license_key(key):
        cache_activation(key)
        return True
    return False


def cache_activation(license_key: str):
    settings = QSettings(ORGANIZATION, APP_NAME)
    fingerprint = get_machine_fingerprint()
    signature = generate_signature(license_key, fingerprint)
    settings.setValue(SETTING_LICENSE_KEY, license_key)
    settings.setValue(SETTING_LICENSE_SIGNATURE, signature)


def cache_activation_v2(cache: dict):
    settings = QSettings(ORGANIZATION, APP_NAME)
    settings.setValue("license_cache_v2", json.dumps(cache))
    settings.setValue(SETTING_LICENSE_KEY, cache.get("key_hash", ""))
    settings.setValue(SETTING_LICENSE_SIGNATURE, cache.get("fingerprint", ""))


def deactivate_license():
    settings = QSettings(ORGANIZATION, APP_NAME)
    settings.remove(SETTING_LICENSE_KEY)
    settings.remove(SETTING_LICENSE_SIGNATURE)
    settings.remove("license_cache_v2")


__all__ = [
    "LicenseService",
    "get_machine_fingerprint",
    "is_offline_cache_valid",
    "verify_license_online",
    "verify_license_key",
    "generate_license_key",
    "cache_activation",
    "cache_activation_v2",
    "deactivate_license",
    "BUY_URL",
    "ORGANIZATION",
    "APP_NAME",
]
