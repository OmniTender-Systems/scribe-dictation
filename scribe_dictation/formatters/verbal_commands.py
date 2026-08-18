"""Smart verbal punctuation and formatting commands parser for dictated speech.

Parses spoken punctuation marks, structural formatting commands (newlines, paragraphs,
bullet points, tabs), and casing commands (all caps, capitalize), while respecting
contextual guardrails to prevent false positives in natural speech.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


SETTINGS_VERBAL_COMMANDS_ENABLED = "verbal_commands_enabled"


# ---------------------------------------------------------------------------
# False-Positive Guardrail Expressions (Phrases that should NOT be parsed as commands)
# ---------------------------------------------------------------------------

_GUARDRAIL_PHRASES: List[Tuple[re.Pattern, str]] = [
    # "a period of time", "period of inactivity", "for a period of", "period tracking", "grace period"
    (
        re.compile(
            r"\b(a|the|this|that|any|each|every|some|long|short|extended|brief|grace)\s+period\b",
            re.IGNORECASE,
        ),
        "\x01PERIOD_NOUN_{}\x02",
    ),
    (
        re.compile(
            r"\bperiod\s+(of|after|before|between|during|time|times|tracker|tracking|costs|piece|drama|pain|pains)\b",
            re.IGNORECASE,
        ),
        "\x01PERIOD_PHRASE_{}\x02",
    ),
    # "comma-separated", "comma separated", "comma splice"
    (
        re.compile(
            r"\bcomma[-\s]+(separated|delimited|splice|splices|placement)\b",
            re.IGNORECASE,
        ),
        "\x01COMMA_PHRASE_{}\x02",
    ),
    # "question mark over", "a question mark", "big question mark"
    (
        re.compile(
            r"\b(a|the|big|huge|giant|another|no)\s+question\s+mark\b", re.IGNORECASE
        ),
        "\x01QUESTION_MARK_{}\x02",
    ),
    (
        re.compile(
            r"\bquestion\s+mark\s+(over|hanging|above|regarding|on)\b", re.IGNORECASE
        ),
        "\x01QUESTION_MARK_PHRASE_{}\x02",
    ),
    # "exclamation mark over", "an exclamation mark"
    (
        re.compile(
            r"\b(an|the|big|huge)\s+exclamation\s+(mark|point)\b", re.IGNORECASE
        ),
        "\x01EXCLAMATION_MARK_{}\x02",
    ),
    # "colon cancer", "colon surgery", "colon cleansing"
    (
        re.compile(
            r"\bcolon\s+(cancer|screening|polyps|surgery|cleansing|hydrotherapy|irrigation|disease|wall|resection)\b",
            re.IGNORECASE,
        ),
        "\x01COLON_MED_{}\x02",
    ),
    # "dollar sign on", "a dollar sign"
    (
        re.compile(r"\b(a|the)\s+dollar\s+sign\b", re.IGNORECASE),
        "\x01DOLLAR_SIGN_{}\x02",
    ),
    # "percent sign" as noun
    (
        re.compile(r"\b(a|the)\s+percent\s+sign\b", re.IGNORECASE),
        "\x01PERCENT_SIGN_{}\x02",
    ),
    # "hashtag" as noun e.g., "trending hashtag", "use the hashtag"
    (
        re.compile(
            r"\b(trending|popular|the|a|this|that|use\s+the|search\s+for\s+the)\s+hashtag\b",
            re.IGNORECASE,
        ),
        "\x01HASHTAG_NOUN_{}\x02",
    ),
]


# ---------------------------------------------------------------------------
# Spoken Command Rules
# ---------------------------------------------------------------------------


class VerbalCommandParser:
    """Parses spoken punctuation, structural, and casing commands in transcribed text."""

    def __init__(self, enabled: bool = True, settings: Optional[Any] = None) -> None:
        self._settings = settings
        self._enabled = enabled
        if self._settings is not None:
            self._load_from_settings()

    def _load_from_settings(self) -> None:
        if self._settings is not None:
            val = self._settings.value(SETTINGS_VERBAL_COMMANDS_ENABLED, "true")
            if isinstance(val, bool):
                self._enabled = val
            elif isinstance(val, str):
                self._enabled = val.lower() in ("true", "1", "yes")
            else:
                self._enabled = bool(val)

    @property
    def is_enabled(self) -> bool:
        """Check if verbal commands parsing is enabled."""
        if self._settings is not None:
            self._load_from_settings()
        return self._enabled

    @is_enabled.setter
    def is_enabled(self, value: bool) -> None:
        """Set enabled status and save to settings if present."""
        self._enabled = bool(value)
        if self._settings is not None:
            self._settings.setValue(
                SETTINGS_VERBAL_COMMANDS_ENABLED, "true" if self._enabled else "false"
            )

    def parse(self, text: str) -> str:
        """Parse spoken commands and return formatted text."""
        if not text or not self.is_enabled:
            return text

        result = text

        # 1. Protect guarded phrases from false positives
        protected_map: Dict[str, str] = {}
        counter = 0

        for pattern, placeholder_template in _GUARDRAIL_PHRASES:

            def _protect(match: re.Match) -> str:
                nonlocal counter
                counter += 1
                ph = placeholder_template.format(counter)
                protected_map[ph] = match.group(0)
                return ph

            result = pattern.sub(_protect, result)

        # 2. Casing commands:
        #    - "all caps [phrase] end all caps" or "all caps [word]"
        result = self._parse_casing_commands(result)

        # 3. Structural & formatting commands:
        #    - "new paragraph" -> \n\n
        #    - "new line" / "newline" -> \n
        #    - "bullet point" / "next bullet" -> \n•
        #    - "tab" -> \t
        result = self._parse_structural_commands(result)

        # 4. Spoken punctuation & symbol commands:
        result = self._parse_punctuation_commands(result)

        # 5. Clean up spacing around punctuation and formatting
        result = self._clean_whitespace_and_punctuation(result)

        # 6. Restore protected guardrail phrases
        for ph, orig in protected_map.items():
            result = result.replace(ph, orig)

        return result

    def _parse_casing_commands(self, text: str) -> str:
        """Handle casing commands such as 'all caps <phrase>' or 'capitalize <word>'."""

        # "all caps [phrase] (end all caps|stop all caps)"
        def _replace_all_caps_delimited(match: re.Match) -> str:
            content = match.group(1)
            return content.upper()

        text = re.sub(
            r"\ball\s+caps\s+(.+?)\s+(?:end\s+all\s+caps|stop\s+all\s+caps)\b",
            _replace_all_caps_delimited,
            text,
            flags=re.IGNORECASE,
        )

        # "all caps <word>" -> uppercase single or sequence of words until punctuation
        def _replace_all_caps_single(match: re.Match) -> str:
            phrase = match.group(1)
            return phrase.upper()

        text = re.sub(
            r"\ball\s+caps\s+([A-Za-z0-9_]+)\b",
            _replace_all_caps_single,
            text,
            flags=re.IGNORECASE,
        )

        # "capitalize <word>" -> title case first letter of next word
        def _replace_capitalize(match: re.Match) -> str:
            word = match.group(1)
            return word.capitalize()

        text = re.sub(
            r"\bcapitalize\s+([A-Za-z0-9_]+)\b",
            _replace_capitalize,
            text,
            flags=re.IGNORECASE,
        )

        return text

    def _parse_structural_commands(self, text: str) -> str:
        """Handle structural formatting commands."""
        # "new paragraph"
        text = re.sub(r"\b(?:new\s+paragraph)\b", "\n\n", text, flags=re.IGNORECASE)

        # "bullet point" / "next bullet"
        text = re.sub(
            r"\b(?:bullet\s+point|next\s+bullet)\b", "\n• ", text, flags=re.IGNORECASE
        )

        # "new line" / "newline"
        text = re.sub(r"\b(?:new\s+line|newline)\b", "\n", text, flags=re.IGNORECASE)

        # "tab" / "tab key"
        text = re.sub(r"\b(?:tab|tab\s+key)\b", "\t", text, flags=re.IGNORECASE)

        return text

    def _parse_punctuation_commands(self, text: str) -> str:
        """Handle spoken punctuation marks and symbol commands."""

        # 1. Multi-word quotation commands first (before standalone 'quote')
        # Replace 'open quote <words> close quote' directly or standalone tokens
        def _replace_quoted(match: re.Match) -> str:
            inner = match.group(1).strip()
            return f'"{inner}"'

        text = re.sub(
            r"\b(?:open\s+quote|start\s+quote)\s*(.+?)\s*(?:close\s+quote|end\s+quote|unquote)\b",
            _replace_quoted,
            text,
            flags=re.IGNORECASE,
        )

        def _replace_single_quoted(match: re.Match) -> str:
            inner = match.group(1).strip()
            return f"'{inner}'"

        text = re.sub(
            r"\b(?:open\s+single\s+quote|start\s+single\s+quote)\s*(.+?)\s*(?:close\s+single\s+quote|end\s+single\s+quote)\b",
            _replace_single_quoted,
            text,
            flags=re.IGNORECASE,
        )

        # Standalone open/close quotes
        text = re.sub(
            r"\b(?:open\s+quote|start\s+quote)\b", '"', text, flags=re.IGNORECASE
        )
        text = re.sub(
            r"\b(?:close\s+quote|end\s+quote|unquote)\b", '"', text, flags=re.IGNORECASE
        )
        text = re.sub(
            r"\b(?:open\s+single\s+quote|start\s+single\s+quote)\b",
            "'",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:close\s+single\s+quote|end\s+single\s+quote)\b",
            "'",
            text,
            flags=re.IGNORECASE,
        )

        # 2. Parentheses
        text = re.sub(
            r"\b(?:open\s+parenthesis|open\s+paren|start\s+parenthesis|start\s+paren)\b",
            "(",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:close\s+parenthesis|close\s+paren|end\s+parenthesis|end\s+paren)\b",
            ")",
            text,
            flags=re.IGNORECASE,
        )

        # 3. Punctuation
        text = re.sub(r"\b(?:full\s+stop|period)\b", ".", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:comma)\b", ",", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:question\s+mark)\b", "?", text, flags=re.IGNORECASE)
        text = re.sub(
            r"\b(?:exclamation\s+mark|exclamation\s+point)\b",
            "!",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\b(?:semicolon|semi-colon)\b", ";", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:colon)\b", ":", text, flags=re.IGNORECASE)
        text = re.sub(
            r"\b(?:ellipsis|dot\s+dot\s+dot)\b", "...", text, flags=re.IGNORECASE
        )
        text = re.sub(
            r"\b(?:hyphen|dash|em\s*dash|en\s*dash)\b", "-", text, flags=re.IGNORECASE
        )

        # 4. Symbols
        text = re.sub(r"\b(?:at\s+sign)\b", "@", text, flags=re.IGNORECASE)
        text = re.sub(
            r"\b(?:hashtag|hash\s+tag|hash\s+sign|pound\s+sign)\b",
            "#",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:dollar\s+sign|dollars\s+sign)\b", "$", text, flags=re.IGNORECASE
        )
        text = re.sub(
            r"\b(?:percent\s+sign|percentage\s+sign)\b", "%", text, flags=re.IGNORECASE
        )

        return text

    def _clean_whitespace_and_punctuation(self, text: str) -> str:
        """Clean up whitespace around punctuation marks, newlines, and brackets."""
        # 1. Remove space before standard trailing punctuation: . , ? ! : ; ) %
        text = re.sub(r"\s+([.,?!:;)%])", r"\1", text)

        # 2. Remove space after opening brackets / symbols: ( $ # @
        text = re.sub(r"([(\$#@])\s+", r"\1", text)

        # 3. Handle hyphens (State - of - the - art -> State-of-the-art)
        text = re.sub(r"(\w)\s*-\s*(\w)", r"\1-\2", text)

        # 4. Collapse multi-spaces (except newlines and tabs)
        text = re.sub(r"[^\S\r\n\t]+", " ", text)

        # 5. Clean spaces around newlines
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)

        # 6. Clean spaces around bullet points (\n• item)
        text = re.sub(r"\n•\s*", "\n• ", text)

        # If a bullet point starts at the very beginning of the string with a leading newline, strip leading newline
        if text.startswith("\n• "):
            text = "• " + text[4:]

        # 7. Clean up spaces around quotes:
        # Strip internal whitespace inside quotation pairs
        text = re.sub(r'"\s*([^"]*?)\s*"', r'"\1"', text)
        text = re.sub(r"'\s*([^']*?)\s*'", r"'\1'", text)
        # Ensure space before open quote when preceded by an alphanumeric character
        text = re.sub(r'([A-Za-z0-9])"', r'\1 "', text)
        # Ensure space after close quote when followed by an alphanumeric character
        text = re.sub(r'"([A-Za-z0-9])', r'" \1', text)
        # Final trim inside quotes if any extra whitespace remains
        text = re.sub(r'"\s+([^"]+?)\s+"', r'"\1"', text)

        # 8. Ensure space after punctuation if followed by letters or digits
        text = re.sub(r"([,?!;:])([A-Za-z])", r"\1 \2", text)
        text = re.sub(r"(\.)([A-Za-z])", r"\1 \2", text)

        # 9. Capitalize sentences after terminal punctuation (. ? !) followed by space or newline
        def _capitalize_match(match: re.Match) -> str:
            prefix = match.group(1)
            char = match.group(2)
            return prefix + char.upper()

        text = re.sub(r"([.?!]\s+)([a-z])", _capitalize_match, text)
        text = re.sub(r"(\n+)([a-z])", _capitalize_match, text)
        text = re.sub(r"(•\s+)([a-z])", _capitalize_match, text)

        return text.strip()


def parse_verbal_commands(text: str, enabled: bool = True) -> str:
    """Convenience function to parse verbal punctuation and formatting commands."""
    parser = VerbalCommandParser(enabled=enabled)
    return parser.parse(text)
