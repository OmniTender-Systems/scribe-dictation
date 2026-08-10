import hashlib
import platform
import uuid
import requests
from PySide6.QtCore import QSettings

ORGANIZATION = "ScribeDictation"
APP_NAME = "Scribe Dictation"

# Licensing Settings Keys
SETTING_LICENSE_KEY = "license_key"
SETTING_LICENSE_SIGNATURE = "license_signature"
SETTING_MACHINE_UUID = "machine_uuid"

# Default configuration (can be updated for production)
LICENSE_PROVIDER = "lemonsqueezy"  # "gumroad" or "lemonsqueezy"
LEMONSQUEEZY_API_URL = "https://api.lemonsqueezy.com/v1/licenses/activate"
GUMROAD_API_URL = "https://api.gumroad.com/v2/licenses/verify"

# TODO: replace with the real product ID once the Lemon Squeezy store exists (see LEMONSQUEEZY_SETUP.md)
PRODUCT_ID = "scribe-dictation-pro"

# NOTE: this salt ships in plaintext with the app, so it offers no protection against a
# determined attacker (anyone can read it and forge a valid offline-cache signature). It
# only guards against casual tampering with the cached QSettings value between honest
# online verifications — it is not DRM.
SECRET_SALT = "scribe-dictation-super-secret-salt-2026"


def get_machine_fingerprint() -> str:
    """Generate a stable, unique hardware fingerprint for the current machine."""
    try:
        # Get MAC address or node identifier
        node = str(uuid.getnode())
        system = platform.system()
        node_name = platform.node()
        raw_id = f"{node}-{system}-{node_name}"
        return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
    except Exception:
        # Fallback to a random UUID saved in QSettings if hardware lookup fails
        settings = QSettings(ORGANIZATION, APP_NAME)
        val = settings.value(SETTING_MACHINE_UUID, "")
        if not val:
            val = str(uuid.uuid4())
            settings.setValue(SETTING_MACHINE_UUID, val)
        return str(val)


def generate_signature(license_key: str, fingerprint: str) -> str:
    """Generate a cryptographic signature combining the key and machine fingerprint."""
    data = f"{license_key}:{fingerprint}:{SECRET_SALT}"
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


def verify_license_online(license_key: str) -> bool:
    """Verify license key against the configured provider's API."""
    license_key = license_key.strip()
    if not license_key:
        return False

    if LICENSE_PROVIDER == "gumroad":
        try:
            response = requests.post(
                GUMROAD_API_URL,
                data={"product_permalink": PRODUCT_ID, "license_key": license_key},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                success = data.get("success", False)
                purchase = data.get("purchase", {})
                refunded = purchase.get("refunded", False)
                chargebacked = purchase.get("chargebacked", False)
                if success and not refunded and not chargebacked:
                    cache_activation(license_key)
                    return True
        except Exception as e:
            print(f"Gumroad verification failed: {e}")

    elif LICENSE_PROVIDER == "lemonsqueezy":
        try:
            response = requests.post(
                LEMONSQUEEZY_API_URL,
                json={
                    "license_key": license_key,
                    "instance_name": get_machine_fingerprint(),
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                # Lemon Squeezy return details
                activated = data.get("activated", False)
                status = data.get("license_key", {}).get("status", "")
                if activated or status == "active":
                    cache_activation(license_key)
                    return True
        except Exception as e:
            print(f"Lemon Squeezy verification failed: {e}")

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
