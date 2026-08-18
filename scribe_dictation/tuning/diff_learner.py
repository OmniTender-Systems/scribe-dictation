"""Diff-Based Continuous Learning Engine for Privacy Scribe.

Analyzes text diffs between original Whisper transcription output and
user-edited final text to automatically discover correction patterns and
candidate ReplacementRules for CustomVocabularyManager.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Sequence

from scribe_dictation.transcribe.vocabulary import (
    CustomVocabularyManager,
    ReplacementRule,
)


@dataclass
class DiffSuggestion:
    """Represents a learned candidate word/phrase replacement."""

    original: str
    replacement: str
    confidence: float = 1.0
    occurrence_count: int = 1
    reason: str = "manual_edit_diff"
    is_regex: bool = False
    case_sensitive: bool = False
    word_boundary: bool = True

    def to_rule(self) -> ReplacementRule:
        """Convert suggestion into a ReplacementRule."""
        return ReplacementRule(
            pattern=self.original,
            replacement=self.replacement,
            is_regex=self.is_regex,
            case_sensitive=self.case_sensitive,
            word_boundary=self.word_boundary,
        )


class DiffLearner:
    """Compares original vs edited transcription to discover replacement rules."""

    def __init__(
        self,
        min_char_len: int = 2,
        max_token_len: int = 5,
    ) -> None:
        self.min_char_len = min_char_len
        self.max_token_len = max_token_len
        self._learned_history: list[DiffSuggestion] = []

    def extract_replacements(
        self,
        original_text: str,
        edited_text: str,
    ) -> list[DiffSuggestion]:
        """Compare original text with edited text and extract replacement candidates.

        Args:
            original_text: Original raw or formatted transcription.
            edited_text: User's manually corrected text.

        Returns:
            List of DiffSuggestion instances.
        """
        if not original_text or not edited_text:
            return []

        orig = original_text.strip()
        edit = edited_text.strip()

        if orig == edit:
            return []

        orig_words = orig.split()
        edit_words = edit.split()

        matcher = difflib.SequenceMatcher(None, orig_words, edit_words)
        suggestions: list[DiffSuggestion] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                orig_chunk = " ".join(orig_words[i1:i2]).strip()
                edit_chunk = " ".join(edit_words[j1:j2]).strip()

                # Clean matching edge punctuation (e.g. "Next JS," -> "Next.js,")
                clean_orig, clean_edit = self._strip_matching_punctuation(
                    orig_chunk, edit_chunk
                )

                if not clean_orig or not clean_edit:
                    continue

                if (
                    clean_orig.lower() == clean_edit.lower()
                    and clean_orig == clean_edit
                ):
                    continue

                # Filter out overly long replacements or micro noise
                orig_split = clean_orig.split()
                edit_split = clean_edit.split()

                if (
                    len(orig_split) > self.max_token_len
                    or len(edit_split) > self.max_token_len
                ):
                    continue

                if (
                    len(clean_orig) < self.min_char_len
                    or len(clean_edit) < self.min_char_len
                ):
                    continue

                # Determine case sensitivity: if difference is strictly casing, mark case sensitive
                case_sensitive = False
                if clean_orig.lower() == clean_edit.lower():
                    case_sensitive = True

                # Calculate confidence score
                similarity = difflib.SequenceMatcher(
                    None, clean_orig.lower(), clean_edit.lower()
                ).ratio()
                confidence = round(max(0.6, similarity), 2)

                suggestion = DiffSuggestion(
                    original=clean_orig,
                    replacement=clean_edit,
                    confidence=confidence,
                    occurrence_count=1,
                    reason=f"Edited '{clean_orig}' to '{clean_edit}'",
                    is_regex=False,
                    case_sensitive=case_sensitive,
                    word_boundary=True,
                )
                suggestions.append(suggestion)

        # Deduplicate suggestions in this diff
        deduped = self._deduplicate_suggestions(suggestions)
        self._learned_history.extend(deduped)
        return deduped

    def apply_to_vocabulary(
        self,
        suggestions: Sequence[DiffSuggestion],
        manager: CustomVocabularyManager,
        min_confidence: float = 0.5,
        save: bool = True,
    ) -> list[ReplacementRule]:
        """Automatically insert suggestions into a CustomVocabularyManager.

        Args:
            suggestions: List of DiffSuggestion items to insert.
            manager: CustomVocabularyManager instance.
            min_confidence: Minimum confidence threshold.
            save: Whether to persist changes after adding.

        Returns:
            List of successfully added ReplacementRule items.
        """
        added_rules: list[ReplacementRule] = []

        for item in suggestions:
            if item.confidence < min_confidence:
                continue

            rule = manager.add_replacement(
                pattern=item.original,
                replacement=item.replacement,
                is_regex=item.is_regex,
                case_sensitive=item.case_sensitive,
                word_boundary=item.word_boundary,
            )
            # Also add replacement word to custom terms vocabulary list for Whisper prompt biasing
            manager.add_word(item.replacement)
            added_rules.append(rule)

        if save and added_rules:
            manager.save()

        return added_rules

    def get_history(self) -> list[DiffSuggestion]:
        """Return history of all extracted suggestions."""
        return list(self._learned_history)

    def clear_history(self) -> None:
        """Clear suggestion history."""
        self._learned_history.clear()

    @staticmethod
    def _strip_matching_punctuation(orig: str, edit: str) -> tuple[str, str]:
        """Strip matching leading/trailing punctuation from both strings."""
        punct = ".,;:!?()\"'`"
        clean_orig = orig.strip(punct).strip()
        clean_edit = edit.strip(punct).strip()
        return clean_orig, clean_edit

    @staticmethod
    def _deduplicate_suggestions(
        suggestions: list[DiffSuggestion],
    ) -> list[DiffSuggestion]:
        """Merge identical suggestions and increment occurrence counts."""
        seen: dict[tuple[str, str], DiffSuggestion] = {}
        for s in suggestions:
            key = (s.original.lower(), s.replacement)
            if key in seen:
                seen[key].occurrence_count += 1
            else:
                seen[key] = s
        return list(seen.values())
