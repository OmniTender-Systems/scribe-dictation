"""Custom Vocabulary & Dictionary Biasing engine (Supervocab) for Privacy Scribe.

Provides:
- ReplacementRule: Dataclass defining exact and regex-based post-transcription replacement rules.
- build_initial_prompt: Builds an optimal initial_prompt string for Whisper models (OpenAI & faster-whisper).
- apply_replacements: Applies word and regex replacements to transcribed text.
- CustomVocabularyManager: Manages custom vocabulary lists, replacement rules, prompt generation, and settings/JSON persistence.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

DEFAULT_APP_DIR_NAME = ".privacy_scribe"
VOCABULARY_FILENAME = "vocabulary.json"
SETTINGS_VOCAB_WORDS_KEY = "custom_vocabulary_words"
SETTINGS_VOCAB_RULES_KEY = "custom_vocabulary_rules"
MAX_PROMPT_CHARS = 1000


def get_default_config_path() -> Path:
    """Return the default configuration file path for custom vocabulary."""
    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            base_dir = Path(app_data) / "PrivacyScribe"
        else:
            base_dir = Path.home() / DEFAULT_APP_DIR_NAME
    else:
        base_dir = Path.home() / DEFAULT_APP_DIR_NAME

    return base_dir / VOCABULARY_FILENAME


@dataclass
class ReplacementRule:
    """Represents a post-transcription replacement rule.

    Attributes:
        pattern: The target string or regex pattern to search for.
        replacement: The replacement string.
        is_regex: Whether the pattern should be treated as a regular expression.
        case_sensitive: Whether matching is case-sensitive.
        word_boundary: For non-regex patterns, whether to enforce whole word boundaries.
    """

    pattern: str
    replacement: str
    is_regex: bool = False
    case_sensitive: bool = False
    word_boundary: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize rule to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplacementRule:
        """Create rule from dictionary."""
        return cls(
            pattern=str(data.get("pattern", "")),
            replacement=str(data.get("replacement", "")),
            is_regex=bool(data.get("is_regex", False)),
            case_sensitive=bool(data.get("case_sensitive", False)),
            word_boundary=bool(data.get("word_boundary", True)),
        )

    def apply(self, text: str) -> str:
        """Apply this replacement rule to the given text."""
        if not self.pattern or not text:
            return text

        flags = 0 if self.case_sensitive else re.IGNORECASE

        if self.is_regex:
            try:
                compiled = re.compile(self.pattern, flags=flags)
                return compiled.sub(self.replacement, text)
            except re.error as e:
                # Malformed user regex: ignore gracefully without crashing
                print(f"Warning: Invalid regex pattern '{self.pattern}': {e}")
                return text

        # Non-regex exact phrase / word replacement
        if self.word_boundary:
            # Check if start / end have word characters to avoid invalid \b boundaries
            prefix = r"\b" if re.match(r"^\w", self.pattern) else ""
            suffix = r"\b" if re.search(r"\w$", self.pattern) else ""
            pattern_regex = f"{prefix}{re.escape(self.pattern)}{suffix}"
        else:
            pattern_regex = re.escape(self.pattern)

        try:
            compiled = re.compile(pattern_regex, flags=flags)
            # Escape backslashes in replacement when using re.sub for plain string replacements
            # so characters like \g or \1 in plain replacements aren't misinterpreted as groups
            safe_replacement = self.replacement.replace("\\", r"\\")
            return compiled.sub(safe_replacement, text)
        except re.error as e:
            print(f"Warning: Error replacing '{self.pattern}': {e}")
            return text


def build_initial_prompt(
    words: Optional[Sequence[str]] = None,
    base_prompt: Optional[str] = None,
    max_chars: int = MAX_PROMPT_CHARS,
) -> str:
    """Build an optimal initial_prompt string for Whisper dictionary biasing.

    Formats custom vocabulary terms into a natural glossary prompt that primes
    Whisper's decoder towards correct terminology, technical jargon, and capitalization.

    Args:
        words: List of custom words or phrases.
        base_prompt: Optional existing prompt or context text.
        max_chars: Maximum character length for the generated prompt string.

    Returns:
        Formatted initial_prompt string.
    """
    clean_words: list[str] = []
    seen = set()

    if words:
        for w in words:
            trimmed = str(w).strip()
            if trimmed and trimmed.lower() not in seen:
                clean_words.append(trimmed)
                seen.add(trimmed.lower())

    base = (base_prompt or "").strip()

    if not clean_words:
        return base[:max_chars] if max_chars else base

    # Build glossary portion
    # Whisper responds very well to "Glossary: Term1, Term2, Term3." or natural list
    terms_str = ", ".join(clean_words)
    glossary_prefix = "Glossary: "

    if base:
        # If base prompt ends without punctuation, add period
        if not base.endswith((".", "!", "?", ":")):
            base += "."
        full_prompt = f"{base} {glossary_prefix}{terms_str}."
    else:
        full_prompt = f"{glossary_prefix}{terms_str}."

    # Enforce max_chars constraint if needed
    if len(full_prompt) <= max_chars:
        return full_prompt

    # Truncate words list until it fits
    current_words = list(clean_words)
    while current_words and len(full_prompt) > max_chars:
        current_words.pop()
        if current_words:
            terms_str = ", ".join(current_words)
            if base:
                full_prompt = f"{base} {glossary_prefix}{terms_str}."
            else:
                full_prompt = f"{glossary_prefix}{terms_str}."
        else:
            full_prompt = base[:max_chars] if base else ""

    return full_prompt


def apply_replacements(
    text: str,
    rules: Optional[Sequence[ReplacementRule]] = None,
) -> str:
    """Apply a sequence of ReplacementRules to text in order.

    Args:
        text: Transcribed text to clean up.
        rules: List of ReplacementRule instances.

    Returns:
        Cleaned text with all replacements applied.
    """
    if not text or not rules:
        return text

    result = text
    for rule in rules:
        if isinstance(rule, ReplacementRule):
            result = rule.apply(result)
        elif isinstance(rule, dict):
            rule_obj = ReplacementRule.from_dict(rule)
            result = rule_obj.apply(result)

    return result


class CustomVocabularyManager:
    """Manages custom vocabulary terms and post-transcription replacement rules.

    Supports:
    - Dictionary biasing prompt generation for Whisper models.
    - Post-transcription exact & regex replacements.
    - Persistence via QSettings and/or JSON config files.
    """

    def __init__(
        self,
        words: Optional[Sequence[str]] = None,
        replacements: Optional[Sequence[ReplacementRule | dict[str, Any]]] = None,
        config_path: Optional[str | Path] = None,
        settings: Optional[Any] = None,
        base_prompt: Optional[str] = None,
        auto_load: bool = True,
    ):
        """Initialize the CustomVocabularyManager.

        Args:
            words: Initial list of custom vocabulary words.
            replacements: Initial list of ReplacementRule objects or dicts.
            config_path: Custom JSON configuration file path.
            settings: Optional QSettings instance for Qt-based persistence.
            base_prompt: Optional base initial prompt.
            auto_load: If True and config_path or settings exist, loads persisted data.
        """
        self._words: list[str] = []
        self._rules: list[ReplacementRule] = []
        self._base_prompt: str = base_prompt or ""
        self._config_path: Optional[Path] = (
            Path(config_path) if config_path else get_default_config_path()
        )
        self._settings = settings

        # Load initial values if provided
        if words is not None:
            self.set_words(words)

        if replacements is not None:
            self.set_replacements(replacements)

        # Auto load from persistence if no explicit in-memory data passed or auto_load requested
        if auto_load and words is None and replacements is None:
            self.load()

    # ── Vocabulary Words Management ──────────────────────────────────

    def add_word(self, word: str) -> bool:
        """Add a custom vocabulary word or phrase if not already present.

        Returns:
            True if word was added, False if it was already present or empty.
        """
        cleaned = word.strip()
        if not cleaned:
            return False

        for existing in self._words:
            if existing.lower() == cleaned.lower():
                return False

        self._words.append(cleaned)
        return True

    def remove_word(self, word: str) -> bool:
        """Remove a vocabulary word (case-insensitive search).

        Returns:
            True if removed, False if not found.
        """
        target = word.strip().lower()
        for idx, existing in enumerate(self._words):
            if existing.lower() == target:
                self._words.pop(idx)
                return True
        return False

    def set_words(self, words: Sequence[str]) -> None:
        """Set the entire list of custom vocabulary words, deduplicating case-insensitively."""
        self._words = []
        seen = set()
        for w in words:
            cleaned = str(w).strip()
            if cleaned and cleaned.lower() not in seen:
                self._words.append(cleaned)
                seen.add(cleaned.lower())

    def get_words(self) -> list[str]:
        """Return a copy of the list of custom vocabulary words."""
        return list(self._words)

    def clear_words(self) -> None:
        """Clear all custom vocabulary words."""
        self._words.clear()

    # ── Replacement Rules Management ─────────────────────────────────

    def add_replacement(
        self,
        pattern: str,
        replacement: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        word_boundary: bool = True,
    ) -> ReplacementRule:
        """Add or update a replacement rule.

        Returns:
            The created ReplacementRule instance.
        """
        rule = ReplacementRule(
            pattern=pattern.strip() if not is_regex else pattern,
            replacement=replacement,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            word_boundary=word_boundary,
        )

        # Remove existing rule with exact same pattern if present
        self.remove_replacement(pattern)
        self._rules.append(rule)
        return rule

    def remove_replacement(self, pattern: str) -> bool:
        """Remove a replacement rule matching the given pattern.

        Returns:
            True if removed, False if not found.
        """
        target = pattern.strip()
        for idx, rule in enumerate(self._rules):
            if rule.pattern.strip() == target or (
                not rule.is_regex
                and not rule.case_sensitive
                and rule.pattern.strip().lower() == target.lower()
            ):
                self._rules.pop(idx)
                return True
        return False

    def set_replacements(
        self,
        rules: Sequence[ReplacementRule | dict[str, Any]],
    ) -> None:
        """Set the list of replacement rules."""
        self._rules = []
        for r in rules:
            if isinstance(r, ReplacementRule):
                self._rules.append(r)
            elif isinstance(r, dict):
                self._rules.append(ReplacementRule.from_dict(r))

    def get_replacements(self) -> list[ReplacementRule]:
        """Return a copy of the list of replacement rules."""
        return list(self._rules)

    def clear_replacements(self) -> None:
        """Clear all replacement rules."""
        self._rules.clear()

    def clear(self) -> None:
        """Clear both vocabulary words and replacement rules."""
        self.clear_words()
        self.clear_replacements()

    # ── Prompt Generation & Transcription Correction ──────────────────

    def build_initial_prompt(
        self,
        extra_words: Optional[Sequence[str]] = None,
        base_prompt: Optional[str] = None,
        max_chars: int = MAX_PROMPT_CHARS,
    ) -> str:
        """Generate Whisper initial_prompt string using managed words and optional extras."""
        combined_words = list(self._words)
        if extra_words:
            combined_words.extend(extra_words)

        effective_base = base_prompt if base_prompt is not None else self._base_prompt
        return build_initial_prompt(
            words=combined_words,
            base_prompt=effective_base,
            max_chars=max_chars,
        )

    def apply_replacements(self, text: str) -> str:
        """Apply all configured replacement rules to the transcribed text."""
        return apply_replacements(text, self._rules)

    # ── Persistence (JSON / QSettings) ────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize manager data to dictionary."""
        return {
            "words": list(self._words),
            "replacements": [rule.to_dict() for rule in self._rules],
            "base_prompt": self._base_prompt,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Populate manager data from dictionary."""
        if not isinstance(data, dict):
            return

        words_data = data.get("words", [])
        if isinstance(words_data, (list, tuple)):
            self.set_words([str(w) for w in words_data])

        replacements_data = data.get("replacements", [])
        if isinstance(replacements_data, (list, tuple)):
            self.set_replacements(replacements_data)

        if "base_prompt" in data:
            self._base_prompt = str(data["base_prompt"])

    def save(self, path: Optional[str | Path] = None) -> None:
        """Save vocabulary and replacement rules to QSettings and/or JSON file."""
        target_path = Path(path) if path else self._config_path

        # 1. Save to QSettings if provided
        if self._settings is not None:
            try:
                self._settings.setValue(SETTINGS_VOCAB_WORDS_KEY, self._words)
                rules_json = json.dumps([r.to_dict() for r in self._rules])
                self._settings.setValue(SETTINGS_VOCAB_RULES_KEY, rules_json)
                if hasattr(self._settings, "sync"):
                    self._settings.sync()
            except Exception as e:
                print(f"Warning: Failed to save vocabulary to QSettings: {e}")

        # 2. Save to JSON config file
        if target_path:
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(
                    f"Warning: Failed to save vocabulary config to {target_path}: {e}"
                )

    def load(self, path: Optional[str | Path] = None) -> None:
        """Load vocabulary and replacement rules from QSettings and/or JSON file."""
        target_path = Path(path) if path else self._config_path
        loaded = False

        # 1. Try loading from QSettings first if provided
        if self._settings is not None:
            try:
                words_val = self._settings.value(SETTINGS_VOCAB_WORDS_KEY)
                rules_val = self._settings.value(SETTINGS_VOCAB_RULES_KEY)

                if words_val is not None:
                    if isinstance(words_val, list):
                        self.set_words(words_val)
                    elif isinstance(words_val, str) and words_val.strip():
                        # Try parsing as JSON array or comma separated
                        try:
                            parsed = json.loads(words_val)
                            if isinstance(parsed, list):
                                self.set_words(parsed)
                        except Exception:
                            self.set_words(
                                [w.strip() for w in words_val.split(",") if w.strip()]
                            )
                    loaded = True

                if (
                    rules_val is not None
                    and isinstance(rules_val, str)
                    and rules_val.strip()
                ):
                    try:
                        parsed_rules = json.loads(rules_val)
                        if isinstance(parsed_rules, list):
                            self.set_replacements(parsed_rules)
                            loaded = True
                    except Exception:
                        pass
            except Exception as e:
                print(f"Warning: Failed to load vocabulary from QSettings: {e}")

        # 2. Load from JSON config file (fallback or primary if QSettings didn't load)
        if not loaded and target_path and target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.from_dict(data)
            except Exception as e:
                print(
                    f"Warning: Failed to load vocabulary config from {target_path}: {e}"
                )
