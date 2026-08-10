import hashlib
import hmac
import platform
import secrets
import uuid

from PySide6.QtCore import QSettings

ORGANIZATION = "ScribeDictation"
APP_NAME = "Scribe Dictation"

# Licensing Settings Keys
SETTING_LICENSE_KEY = "license_key"
SETTING_LICENSE_SIGNATURE = "license_signature"
SETTING_MACHINE_UUID = "machine_uuid"

# Self-signed licensing: keys are generated offline (scripts/generate_license.py)
# and verified locally by this module. No third-party licensing API (Lemon Squeezy,
# Gumroad) is required or called — avoids depending on an account that may not exist
# yet, and avoids a per-verification network call entirely.
#
# NOTE: LICENSE_SECRET ships in plaintext in the app, so a determined attacker can
# read it and mint their own valid-looking keys. Same threat model as the previous
# offline-cache salt: this deters casual piracy, it is not DRM.
LICENSE_SECRET = "scribe-dictation-super-secret-salt-2026"

KEY_PREFIX = "SCRIBE"

# Where the "Buy Pro" button sends people. The buy/payment flow lives on the
# storefront (Stripe Payment Link + crypto option), not in this app — after payment,
# the buyer gets a key by email (generated with scripts/generate_license.py).
BUY_URL = "https://nexiex.com/#buy"


def get_machine_fingerprint() -> str:
    """Generate a stable, unique hardware fingerprint for the current machine."""
    try:
        node = str(uuid.getnode())
        system = platform.system()
        node_name = platform.node()
        raw_id = f"{node}-{system}-{node_name}"
        return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
    except Exception:
        settings = QSettings(ORGANIZATION, APP_NAME)
        val = settings.value(SETTING_MACHINE_UUID, "")
        if not val:
            val = str(uuid.uuid4())
            settings.setValue(SETTING_MACHINE_UUID, val)
        return str(val)


def generate_signature(license_key: str, fingerprint: str) -> str:
    """Generate a signature binding a license key to this machine, for the offline cache."""
    data = f"{license_key}:{fingerprint}:{LICENSE_SECRET}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def is_offline_cache_valid() -> bool:
    """Check if the locally cached activation signature is valid for this machine."""
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
    """Mint a new license key. Run offline after a payment comes in (Stripe/crypto),
    then send the printed key to the buyer by email. Not called from the app itself."""
    body = "-".join(secrets.token_hex(2).upper() for _ in range(3))
    return f"{KEY_PREFIX}-{body}-{_checksum(body).upper()}"


def verify_license_key(license_key: str) -> bool:
    """Verify a license key's self-contained signature. No network call."""
    license_key = license_key.strip().upper()
    parts = license_key.split("-")
    if len(parts) != 5 or parts[0] != KEY_PREFIX:
        return False
    body = "-".join(parts[1:4])
    expected = _checksum(body).upper()
    return hmac.compare_digest(parts[4], expected)


def verify_license_online(license_key: str) -> bool:
    """Verify a license key and, if valid, cache it for offline use.

    Named for compatibility with the activation UI; despite the name this performs
    no network call — verification is entirely local (see verify_license_key).
    """
    license_key = license_key.strip()
    if not license_key:
        return False
    if verify_license_key(license_key):
        cache_activation(license_key)
        return True
    return False


def cache_activation(license_key: str):
    """Store the activation signature and license key locally for offline usage."""
    settings = QSettings(ORGANIZATION, APP_NAME)
    fingerprint = get_machine_fingerprint()
    signature = generate_signature(license_key, fingerprint)
    settings.setValue(SETTING_LICENSE_KEY, license_key)
    settings.setValue(SETTING_LICENSE_SIGNATURE, signature)


def deactivate_license():
    """Clear local activation state."""
    settings = QSettings(ORGANIZATION, APP_NAME)
    settings.remove(SETTING_LICENSE_KEY)
    settings.remove(SETTING_LICENSE_SIGNATURE)
