"""Machine fingerprint generation for license binding.

Produces a stable hardware hash from available machine identifiers.
This is an obfuscation + deterrent layer — not DRM-grade.
A motivated attacker can spoof MAC/CPU, but it raises the bar far above
a plain QSettings boolean or a license key that works on any machine.
"""

import hashlib
import os
import socket
import subprocess
from typing import Optional


def _get_mac_address() -> Optional[str]:
    """Return the MAC address of the first non-loopback interface."""
    try:
        import uuid
        mac = uuid.getnode()
        if mac is not None and (mac >> 40) & 1 == 0:
            return mac.to_bytes(6, "big").hex(":")
    except Exception:
        pass
    return None


def _get_hostname() -> str:
    return socket.gethostname()


def _get_cpu_identifier() -> str:
    """Cross-platform CPU identifier string."""
    if os.name == "nt":  # Windows
        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "ProcessorId"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    return lines[1].strip()
        except Exception:
            pass

    # Fallback: platform info
    import platform
    return platform.processor() or platform.machine() or "unknown"


def get_machine_fingerprint() -> str:
    """Return a stable SHA-256 hex digest binding this machine.

    Composited from: MAC address, hostname, CPU identifier.
    Returns the same value on repeated calls (stable hash).
    """
    raw_parts = [
        _get_mac_address() or "no-mac",
        _get_hostname(),
        _get_cpu_identifier(),
    ]
    composite = "|".join(raw_parts)
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()