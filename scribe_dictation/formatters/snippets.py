"""Voice Snippets & Macro Expander Engine for Privacy Scribe Pro.

Provides:
- VoiceSnippet: Dataclass representing a trigger phrase to expansion template mapping.
- expand_variables: Variable substitution engine for {date}, {time}, {clipboard}, {cursor}, {uuid}.
- VoiceSnippetManager: Manages voice snippets, detects triggers in transcribed output (whole-phrase
  and embedded matching), and expands them into rich formatted templates.
- Persistence via QSettings and/or JSON config files.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    import pyperclip
except ImportError:
    pyperclip = None  # type: ignore

try:
    from PySide6.QtCore import QSettings
except ImportError:
    QSettings = None  # type: ignore


DEFAULT_APP_DIR_NAME = ".privacy_scribe"
SNIPPETS_FILENAME = "snippets.json"
SETTINGS_SNIPPETS_CONFIG = "snippets_config"
SETTINGS_SNIPPETS_ENABLED = "snippets_enabled"


def get_default_snippets_path() -> Path:
    """Return the default configuration file path for voice snippets."""
    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            base_dir = Path(app_data) / "PrivacyScribe"
        else:
            base_dir = Path.home() / DEFAULT_APP_DIR_NAME
    else:
        base_dir = Path.home() / DEFAULT_APP_DIR_NAME

    return base_dir / SNIPPETS_FILENAME


@dataclass
class VoiceSnippet:
    """Represents a voice snippet / macro rule.

    Attributes:
        trigger_phrase: Spoken trigger phrase that activates expansion (e.g. "insert signature").
        expansion_template: Template text containing optional variables like {date}, {time}, {clipboard}, {cursor}, {uuid}.
        enabled: Whether the snippet is active.
        description: User-friendly description or title of the snippet.
    """

    trigger_phrase: str
    expansion_template: str
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize snippet to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VoiceSnippet:
        """Create snippet from dictionary."""
        return cls(
            trigger_phrase=str(data.get("trigger_phrase", "")).strip(),
            expansion_template=str(data.get("expansion_template", "")),
            enabled=bool(data.get("enabled", True)),
            description=str(data.get("description", "")).strip(),
        )


# Default built-in starter templates
DEFAULT_VOICE_SNIPPETS: List[VoiceSnippet] = [
    VoiceSnippet(
        trigger_phrase="insert signature",
        expansion_template="Best regards,\n[Your Name]\nPrivacy Scribe Pro",
        enabled=True,
        description="Professional email signature sign-off",
    ),
    VoiceSnippet(
        trigger_phrase="insert date",
        expansion_template="{date}",
        enabled=True,
        description="Current date (YYYY-MM-DD)",
    ),
    VoiceSnippet(
        trigger_phrase="insert time",
        expansion_template="{time}",
        enabled=True,
        description="Current time (HH:MM:SS)",
    ),
    VoiceSnippet(
        trigger_phrase="meeting notes template",
        expansion_template=(
            "# Meeting Notes - {date}\n\n"
            "**Attendees:**\n- \n\n"
            "**Agenda:**\n- \n\n"
            "**Discussion:**\n- \n\n"
            "**Action Items:**\n- [ ] {cursor}"
        ),
        enabled=True,
        description="Structured meeting notes template",
    ),
    VoiceSnippet(
        trigger_phrase="bug report template",
        expansion_template=(
            "### Bug Report\n"
            "**Date:** {date}\n\n"
            "**Description:**\n{cursor}\n\n"
            "**Steps to Reproduce:**\n1. \n\n"
            "**Expected Result:**\n\n"
            "**Actual Result:**\n"
        ),
        enabled=True,
        description="Software bug report template",
    ),
    VoiceSnippet(
        trigger_phrase="clipboard quote",
        expansion_template="> {clipboard}",
        enabled=True,
        description="Quote current clipboard content in markdown",
    ),
    VoiceSnippet(
        trigger_phrase="insert uuid",
        expansion_template="{uuid}",
        enabled=True,
        description="Unique Identifier UUIDv4",
    ),
]


def expand_variables(
    template: str,
    clipboard_text: Optional[str] = None,
    current_dt: Optional[datetime] = None,
    custom_vars: Optional[Dict[str, str]] = None,
) -> str:
    """Expand dynamic variables within a snippet template.

    Supported variables:
    - {date}: Current date (e.g. 2026-08-17)
    - {time}: Current time (e.g. 14:30:00)
    - {datetime}: Current date and time (e.g. 2026-08-17 14:30:00)
    - {clipboard}: Current clipboard contents
    - {cursor}: Cursor position marker (preserved or customized)
    - {uuid}: Newly generated UUIDv4 string

    Args:
        template: Template text containing placeholder variables.
        clipboard_text: Optional clipboard string override (useful for testing or non-GUI).
        current_dt: Optional datetime override (useful for deterministic testing).
        custom_vars: Optional dictionary of additional variable substitutions.

    Returns:
        Expanded text string with variables substituted.
    """
    if not template:
        return ""

    dt = current_dt or datetime.now()

    # Resolve clipboard content safely
    if clipboard_text is not None:
        clip_content = str(clipboard_text)
    else:
        clip_content = ""
        if pyperclip is not None:
            try:
                clip_content = pyperclip.paste() or ""
            except Exception:
                clip_content = ""

    var_map: Dict[str, Any] = {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "clipboard": clip_content,
        "cursor": "{cursor}",  # preserve {cursor} tag in template output
        "uuid": str(uuid.uuid4()),
    }

    if custom_vars:
        var_map.update(custom_vars)

    result = template
    for key, value in var_map.items():
        # Case-insensitive variable placeholder substitution: {date}, {DATE}, etc.
        pattern = re.compile(re.escape(f"{{{key}}}"), re.IGNORECASE)
        val_str = str(value)
        result = pattern.sub(lambda _: val_str, result)

    return result


class VoiceSnippetManager:
    """Manages voice snippets, trigger detection, variable expansions, and persistence."""

    def __init__(
        self,
        snippets: Optional[Sequence[VoiceSnippet | Dict[str, Any]]] = None,
        enabled: bool = True,
        config_path: Optional[str | Path] = None,
        settings: Optional[Any] = None,
        auto_load: bool = True,
    ):
        """Initialize the VoiceSnippetManager.

        Args:
            snippets: Optional initial list of snippets.
            enabled: Whether voice snippet expansion is globally enabled.
            config_path: Custom JSON configuration file path.
            settings: Optional QSettings instance for Qt-based persistence.
            auto_load: If True and no explicit snippets provided, loads from settings/JSON.
        """
        self._snippets: List[VoiceSnippet] = []
        self.enabled: bool = enabled
        self._config_path: Optional[Path] = (
            Path(config_path) if config_path else get_default_snippets_path()
        )
        self._settings = settings

        if snippets is not None:
            self.set_snippets(snippets)
        elif auto_load:
            self.load()

        # If no snippets loaded or present, populate with default templates
        if not self._snippets and (snippets is None):
            self.reset_to_defaults(save_after=False)

    # ── Snippet Management ──────────────────────────────────────────────

    def add_snippet(
        self,
        trigger_phrase: str,
        expansion_template: str,
        enabled: bool = True,
        description: str = "",
    ) -> VoiceSnippet:
        """Add or update a voice snippet by trigger phrase."""
        trigger = trigger_phrase.strip()
        existing = self.get_snippet(trigger)
        if existing:
            existing.expansion_template = expansion_template
            existing.enabled = enabled
            if description:
                existing.description = description
            snippet = existing
        else:
            snippet = VoiceSnippet(
                trigger_phrase=trigger,
                expansion_template=expansion_template,
                enabled=enabled,
                description=description,
            )
            self._snippets.append(snippet)

        self.save()
        return snippet

    def remove_snippet(self, trigger_phrase: str) -> bool:
        """Remove a snippet by trigger phrase (case-insensitive)."""
        target = trigger_phrase.strip().lower()
        orig_len = len(self._snippets)
        self._snippets = [
            s for s in self._snippets if s.trigger_phrase.strip().lower() != target
        ]
        removed = len(self._snippets) < orig_len
        if removed:
            self.save()
        return removed

    def get_snippet(self, trigger_phrase: str) -> Optional[VoiceSnippet]:
        """Find a snippet by trigger phrase (case-insensitive)."""
        target = trigger_phrase.strip().lower()
        for snippet in self._snippets:
            if snippet.trigger_phrase.strip().lower() == target:
                return snippet
        return None

    def get_snippets(self) -> List[VoiceSnippet]:
        """Return a copy of the list of all voice snippets."""
        return list(self._snippets)

    def set_snippets(self, snippets: Sequence[VoiceSnippet | Dict[str, Any]]) -> None:
        """Set the entire list of snippets."""
        self._snippets = []
        for s in snippets:
            if isinstance(s, VoiceSnippet):
                self._snippets.append(s)
            elif isinstance(s, dict):
                self._snippets.append(VoiceSnippet.from_dict(s))

    def clear_snippets(self) -> None:
        """Clear all snippets."""
        self._snippets.clear()
        self.save()

    def set_snippet_enabled(self, trigger_phrase: str, enabled: bool) -> bool:
        """Toggle enabled state for a snippet."""
        snippet = self.get_snippet(trigger_phrase)
        if snippet:
            snippet.enabled = enabled
            self.save()
            return True
        return False

    def reset_to_defaults(self, save_after: bool = True) -> None:
        """Reset snippets to the default built-in starter templates."""
        self._snippets = [
            VoiceSnippet(
                trigger_phrase=s.trigger_phrase,
                expansion_template=s.expansion_template,
                enabled=s.enabled,
                description=s.description,
            )
            for s in DEFAULT_VOICE_SNIPPETS
        ]
        if save_after:
            self.save()

    # ── Expansion Engine ────────────────────────────────────────────────

    def expand_text(
        self,
        text: str,
        clipboard_text: Optional[str] = None,
        current_dt: Optional[datetime] = None,
    ) -> str:
        """Detect trigger phrases in transcribed text and expand into formatted templates.

        Supports:
        - Standalone trigger matching (e.g. "insert signature" or "insert signature.")
        - Embedded trigger matching within larger sentences
        - Case-insensitive matching with flexible whitespace
        - Dynamic variable substitutions ({date}, {time}, {clipboard}, {cursor}, {uuid})
        - Longest trigger matching priority to avoid substring collisions
        """
        if not self.enabled or not text or not text.strip():
            return text

        active_snippets = [
            s for s in self._snippets if s.enabled and s.trigger_phrase.strip()
        ]
        if not active_snippets:
            return text

        # Sort by trigger phrase length descending to match longer phrases first
        active_snippets.sort(key=lambda s: len(s.trigger_phrase.strip()), reverse=True)

        cleaned_text = text.strip()

        # 1. Whole-Phrase / Standalone Trigger Check
        # If the user speaks solely the trigger phrase (with optional punctuation like '.', '!', '?')
        for snippet in active_snippets:
            trigger_escaped = re.escape(snippet.trigger_phrase.strip())
            # Match entire string with optional punctuation and whitespace
            standalone_regex = re.compile(
                rf"^\s*[\"']?{trigger_escaped}[\"']?[\.\,\!\?]?\s*$",
                re.IGNORECASE,
            )
            if standalone_regex.match(cleaned_text):
                return expand_variables(
                    snippet.expansion_template,
                    clipboard_text=clipboard_text,
                    current_dt=current_dt,
                )

        # 2. Embedded Trigger Replacement
        result = text
        for snippet in active_snippets:
            trigger_clean = snippet.trigger_phrase.strip()
            trigger_words = [re.escape(w) for w in trigger_clean.split()]
            if not trigger_words:
                continue

            # Only enforce \b word boundaries if trigger starts/ends with word characters
            prefix = r"\b" if re.match(r"^\w", trigger_clean) else ""
            suffix = r"\b" if re.search(r"\w$", trigger_clean) else ""
            pattern_str = f"{prefix}" + r"\s+".join(trigger_words) + f"{suffix}"
            pattern = re.compile(pattern_str, re.IGNORECASE)

            if pattern.search(result):
                expanded_content = expand_variables(
                    snippet.expansion_template,
                    clipboard_text=clipboard_text,
                    current_dt=current_dt,
                )
                result = pattern.sub(lambda _: expanded_content, result)

        return result

    # ── Persistence ─────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to a dictionary."""
        return {
            "enabled": self.enabled,
            "snippets": [s.to_dict() for s in self._snippets],
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Populate configuration from a dictionary."""
        if not isinstance(data, dict):
            return

        if "enabled" in data:
            self.enabled = bool(data["enabled"])

        snippets_data = data.get("snippets", [])
        if isinstance(snippets_data, (list, tuple)):
            self.set_snippets(snippets_data)

    def save(self, path: Optional[str | Path] = None) -> None:
        """Save snippets configuration to QSettings and/or JSON file."""
        target_path = Path(path) if path else self._config_path

        # 1. Save to QSettings if available
        if self._settings is not None:
            try:
                self._settings.setValue(SETTINGS_SNIPPETS_ENABLED, self.enabled)
                snippets_json = json.dumps([s.to_dict() for s in self._snippets])
                self._settings.setValue(SETTINGS_SNIPPETS_CONFIG, snippets_json)
                if hasattr(self._settings, "sync"):
                    self._settings.sync()
            except Exception as e:
                print(f"Warning: Failed to save snippets to QSettings: {e}")

        # 2. Save to JSON config file
        if target_path:
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Warning: Failed to save snippets config to {target_path}: {e}")

    def load(self, path: Optional[str | Path] = None) -> None:
        """Load snippets configuration from QSettings and/or JSON file."""
        target_path = Path(path) if path else self._config_path
        loaded = False

        # 1. Load from QSettings if available
        if self._settings is not None:
            try:
                enabled_val = self._settings.value(SETTINGS_SNIPPETS_ENABLED)
                if enabled_val is not None:
                    if isinstance(enabled_val, bool):
                        self.enabled = enabled_val
                    elif isinstance(enabled_val, str):
                        self.enabled = enabled_val.lower() == "true"

                snippets_val = self._settings.value(SETTINGS_SNIPPETS_CONFIG)
                if (
                    snippets_val is not None
                    and isinstance(snippets_val, str)
                    and snippets_val.strip()
                ):
                    try:
                        parsed = json.loads(snippets_val)
                        if isinstance(parsed, list):
                            self.set_snippets(parsed)
                            loaded = True
                    except Exception:
                        pass
            except Exception as e:
                print(f"Warning: Failed to load snippets from QSettings: {e}")

        # 2. Load from JSON config file
        if not loaded and target_path and target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.from_dict(data)
                    loaded = True
            except Exception as e:
                print(
                    f"Warning: Failed to load snippets config from {target_path}: {e}"
                )
