"""GitHub release update checker for Privacy Scribe."""

import logging
import re
import urllib.request
import json
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

CURRENT_VERSION = "0.3.0"
GITHUB_REPO = "subtiliorars-sys/scribe-dictation"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
LATEST_RELEASE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"


def parse_version(v: str) -> Tuple[int, ...]:
    """Parse version string like 'v0.2.1' or '0.2.0' into an integer tuple."""
    clean = re.sub(r"^[^\d]*", "", v.strip())
    parts = []
    for chunk in clean.split("."):
        try:
            parts.append(int(re.match(r"^\d+", chunk).group(0)))
        except (AttributeError, ValueError):
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(latest_tag: str, current_version: str = CURRENT_VERSION) -> bool:
    """Compare remote release tag against current version."""
    try:
        latest_parts = parse_version(latest_tag)
        current_parts = parse_version(current_version)
        return latest_parts > current_parts
    except Exception as e:
        logger.debug(f"Failed to compare versions: {e}")
        return False


def fetch_latest_release_info(timeout: float = 4.0) -> Optional[dict]:
    """Fetch latest release metadata from GitHub API."""
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_API,
            headers={
                "User-Agent": f"PrivacyScribe/{CURRENT_VERSION}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag_name = data.get("tag_name", "")
                if tag_name and is_newer_version(tag_name, CURRENT_VERSION):
                    return {
                        "tag_name": tag_name,
                        "name": data.get("name", tag_name),
                        "html_url": data.get("html_url", LATEST_RELEASE_URL),
                        "body": data.get("body", ""),
                        "published_at": data.get("published_at", ""),
                    }
    except Exception as e:
        logger.debug(f"Update check failed (offline or rate limited): {e}")
    return None
