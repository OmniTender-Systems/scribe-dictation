"""AI Formatting Modes and Prompt Preset Engine for Scribe Dictation.

Provides rule-based offline cleaners and LLM prompt presets for converting raw
dictated speech into cleanly formatted content (clean text, bullets, emails,
meeting notes, code comments, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Protocol, Sequence, Union


# ---------------------------------------------------------------------------
# Offline Rule-Based Cleaners
# ---------------------------------------------------------------------------

# Common English filler words and phrases
FILLER_PATTERNS = [
    r"\bum+\b",
    r"\buh+\b",
    r"\bah+\b",
    r"\ber+\b",
    r"\bhm+\b",
    r"\bhmm+\b",
    r"\blike\b",
    r"\byou know\b",
    r"\bsort of\b",
    r"\bkind of\b",
    r"\bi mean\b",
    r"\bbasically\b",
    r"\bactually\b",
]

_COMPILED_FILLER_RE = re.compile(
    r"\b(?:" + "|".join(FILLER_PATTERNS) + r")\b[,.]?",
    re.IGNORECASE,
)

NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}

_NUMBER_WORD_RE = re.compile(
    r"\b(" + "|".join(NUMBER_WORDS.keys()) + r")\b",
    re.IGNORECASE,
)


def clean_filler_words(text: str) -> str:
    """Remove conversational filler words and phrases while preserving surrounding structure."""
    if not text:
        return text

    # Replace fillers
    cleaned = _COMPILED_FILLER_RE.sub("", text)
    # Collapse multiple spaces and clean dangling spaces before punctuation
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.?!;:])", r"\1", cleaned)
    return cleaned.strip()


def clean_stutters(text: str) -> str:
    """Remove immediate word repetitions (stuttering), e.g. 'the the' -> 'the'."""
    if not text:
        return text

    # Match consecutive identical words separated by space or hyphen
    pattern = r"\b([A-Za-z0-9]+)(?:[- ]+\1\b)+"
    cleaned = re.sub(pattern, r"\1", text, flags=re.IGNORECASE)
    return cleaned


def clean_numbers(text: str) -> str:
    """Convert common spoken single-digit/small number words to numeric digits."""
    if not text:
        return text

    def _replace_num(match: re.Match) -> str:
        word = match.group(1).lower()
        return NUMBER_WORDS.get(word, match.group(0))

    return _NUMBER_WORD_RE.sub(_replace_num, text)


def clean_punctuation_and_capitalization(text: str) -> str:
    """Fix common capitalization and punctuation issues (capitalizing sentence starts)."""
    if not text:
        return text

    cleaned = text.strip()
    if not cleaned:
        return ""

    # Ensure sentence start is capitalized
    sentences = re.split(r"([.?!]\s+)", cleaned)
    result = []
    for part in sentences:
        if part and not re.match(r"^[.?!]\s+$", part):
            part = part[0].upper() + part[1:] if len(part) > 1 else part.upper()
        result.append(part)

    cleaned = "".join(result)
    # Ensure ending punctuation if not present
    if cleaned and cleaned[-1] not in ".?!;:\"'`)>]}":
        cleaned += "."
    return cleaned


# ---------------------------------------------------------------------------
# Formatting Mode Dataclass & Built-ins
# ---------------------------------------------------------------------------

CleanerFunc = Callable[[str], str]


@dataclass(frozen=True)
class FormattingMode:
    """Represents a transcription formatting mode or preset."""

    id: str
    name: str
    description: str
    system_prompt: str
    is_pro: bool = False
    rule_cleaners: Sequence[CleanerFunc] = field(default_factory=tuple)


RAW_MODE = FormattingMode(
    id="raw",
    name="Raw Verbatim",
    description="Exact verbatim speech without modification or filler removal.",
    system_prompt="",
    is_pro=False,
    rule_cleaners=(),
)

CLEAN_MODE = FormattingMode(
    id="clean",
    name="Clean Speech",
    description="Removes filler words, stutters, and cleans punctuation/capitalization while preserving exact meaning.",
    system_prompt=(
        "You are an expert editor. Clean up the provided transcribed speech by removing conversational filler words "
        "(um, uh, like, you know, kind of, sort of, basically), fixing stutters or repeated words, and ensuring "
        "flawless punctuation and capitalization without changing the original speaker's intent or meaning. "
        "Output ONLY the cleaned transcription text without any conversational preamble or notes."
    ),
    is_pro=False,
    rule_cleaners=(
        clean_stutters,
        clean_filler_words,
        clean_punctuation_and_capitalization,
    ),
)

BULLETS_MODE = FormattingMode(
    id="bullets",
    name="Bullet Points",
    description="Formats transcribed speech into clean, crisp markdown bullet points.",
    system_prompt=(
        "You are an expert executive assistant. Convert the following transcribed speech into crisp, clear, "
        "and concise markdown bullet points summarizing key concepts and statements. Output ONLY the markdown bullet list."
    ),
    is_pro=True,
    rule_cleaners=(
        clean_stutters,
        clean_filler_words,
    ),
)

MEETING_NOTES_MODE = FormattingMode(
    id="meeting_notes",
    name="Meeting Notes",
    description="Structures speech into Summary, Key Decisions, and Action Items.",
    system_prompt=(
        "You are an executive scribe. Structure the following spoken meeting transcript into formatted markdown with:\n"
        "### Summary\n<1-2 sentence executive overview>\n\n"
        "### Key Decisions\n- <bullet points of decisions>\n\n"
        "### Action Items\n- [ ] <task with owner if mentioned>\n\n"
        "Output ONLY the structured markdown."
    ),
    is_pro=True,
    rule_cleaners=(
        clean_stutters,
        clean_filler_words,
    ),
)

EMAIL_MODE = FormattingMode(
    id="email",
    name="Email Draft",
    description="Drafts a polite, professional, and well-structured email from spoken points.",
    system_prompt=(
        "You are an executive communications expert. Convert the spoken transcript into a polite, clear, and professional "
        "email draft including Subject line, greeting, concise body paragraphs, and professional sign-off. "
        "Output ONLY the email draft."
    ),
    is_pro=True,
    rule_cleaners=(
        clean_stutters,
        clean_filler_words,
    ),
)

CODE_COMMENT_MODE = FormattingMode(
    id="code_comment",
    name="Code Comment / Docstring",
    description="Formats speech into clean Python/programming docstrings and code comments.",
    system_prompt=(
        "You are a senior software engineer. Convert the spoken explanation into a clean, standard programming docstring "
        "and clear inline code comments matching PEP 257 / Google style. Output ONLY the formatted comments/docstrings."
    ),
    is_pro=True,
    rule_cleaners=(
        clean_stutters,
        clean_filler_words,
    ),
)

SUMMARY_MODE = FormattingMode(
    id="summary",
    name="Executive Summary",
    description="Structures text into a concise executive summary with key takeaways.",
    system_prompt=(
        "You are an executive assistant. Convert the provided text into a clear, concise executive summary "
        "highlighting the core message and key takeaways. Output ONLY the formatted summary without conversational notes."
    ),
    is_pro=True,
    rule_cleaners=(
        clean_stutters,
        clean_filler_words,
    ),
)

TRANSLATE_EN_MODE = FormattingMode(
    id="translate_en",
    name="Translate to English",
    description="Translates the provided text into fluent, natural English.",
    system_prompt=(
        "You are an expert translator. Translate the following text into clear, fluent, natural English. "
        "Output ONLY the translated text without conversational preamble or notes."
    ),
    is_pro=True,
    rule_cleaners=(),
)

BUILTIN_MODES: Dict[str, FormattingMode] = {
    RAW_MODE.id: RAW_MODE,
    CLEAN_MODE.id: CLEAN_MODE,
    BULLETS_MODE.id: BULLETS_MODE,
    MEETING_NOTES_MODE.id: MEETING_NOTES_MODE,
    EMAIL_MODE.id: EMAIL_MODE,
    CODE_COMMENT_MODE.id: CODE_COMMENT_MODE,
}

TRANSFORM_MODES: Dict[str, FormattingMode] = {
    "clean": CLEAN_MODE,
    "grammar": CLEAN_MODE,
    "bullets": BULLETS_MODE,
    "email": EMAIL_MODE,
    "meeting_notes": MEETING_NOTES_MODE,
    "summary": SUMMARY_MODE,
    "translate_en": TRANSLATE_EN_MODE,
    "code_comment": CODE_COMMENT_MODE,
}


def get_mode_by_id(mode_id: str) -> Optional[FormattingMode]:
    """Retrieve a FormattingMode by its ID or None if not found."""
    cleaned_id = str(mode_id).lower().strip()
    return BUILTIN_MODES.get(cleaned_id) or TRANSFORM_MODES.get(cleaned_id)


# ---------------------------------------------------------------------------
# LLM Client Protocol & Fallbacks
# ---------------------------------------------------------------------------


class LLMCallable(Protocol):
    def __call__(self, system_prompt: str, user_text: str) -> str: ...


# ---------------------------------------------------------------------------
# Format Engine
# ---------------------------------------------------------------------------


class FormatEngine:
    """Applies rule-based cleaning, verbal command parsing, and optional LLM formatting to transcription text."""

    def __init__(
        self,
        llm_client: Optional[Union[LLMCallable, Any]] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        mode: Optional[Union[str, FormattingMode]] = None,
        verbal_commands_enabled: bool = True,
        verbal_command_parser: Optional[Any] = None,
    ) -> None:
        self.llm_client = llm_client
        self.api_key = api_key
        self.model = model
        self.default_mode = mode or RAW_MODE
        if verbal_command_parser is not None:
            self.verbal_command_parser = verbal_command_parser
        else:
            from scribe_dictation.formatters.verbal_commands import VerbalCommandParser

            self.verbal_command_parser = VerbalCommandParser(
                enabled=verbal_commands_enabled
            )

    def format_text(
        self,
        text: str,
        mode: Optional[Union[str, FormattingMode]] = None,
        use_llm: bool = True,
    ) -> str:
        """Convenience method for format using default or specified mode."""
        target_mode = mode if mode is not None else self.default_mode
        return self.format(text, mode=target_mode, use_llm=use_llm)

    def get_mode(self, mode: Union[str, FormattingMode]) -> FormattingMode:
        """Resolve a mode identifier or mode object to a valid FormattingMode."""
        if isinstance(mode, FormattingMode):
            return mode
        mode_id = str(mode).lower().strip()
        if mode_id in BUILTIN_MODES:
            return BUILTIN_MODES[mode_id]
        if mode_id in TRANSFORM_MODES:
            return TRANSFORM_MODES[mode_id]
        raise ValueError(
            f"Unknown formatting mode: '{mode}'. Available modes: {list(BUILTIN_MODES.keys())}"
        )

    def transform(
        self,
        text: str,
        action: str,
        custom_instruction: str = "",
        use_llm: bool = True,
    ) -> str:
        """Transform text using a preset action (clean, bullets, email, summary, translate_en) or custom instruction."""
        if not text or not text.strip():
            return text

        action_id = str(action).lower().strip()

        if action_id == "custom":
            instruction = (
                custom_instruction.strip()
                if custom_instruction
                else "Improve clarity and grammar"
            )
            custom_mode = FormattingMode(
                id="custom",
                name="Custom Instruction",
                description=instruction,
                system_prompt=(
                    f"You are an expert AI writing and editing assistant. Follow this instruction carefully: {instruction}\n\n"
                    "Apply this instruction to the following text. Output ONLY the resulting transformed text without any introductory conversation or notes."
                ),
                is_pro=True,
                rule_cleaners=(clean_stutters, clean_filler_words),
            )
            return self.format(text, mode=custom_mode, use_llm=use_llm)

        if action_id in TRANSFORM_MODES:
            return self.format(text, mode=TRANSFORM_MODES[action_id], use_llm=use_llm)
        if action_id in BUILTIN_MODES:
            return self.format(text, mode=BUILTIN_MODES[action_id], use_llm=use_llm)

        return self.format(text, mode=action, use_llm=use_llm)

    def clean_rule_based(self, text: str, mode: Union[str, FormattingMode]) -> str:
        """Apply verbal commands parsing and all offline rule cleaners configured for the given mode."""
        formatting_mode = self.get_mode(mode)
        result = text
        if self.verbal_command_parser is not None and getattr(
            self.verbal_command_parser, "is_enabled", True
        ):
            result = self.verbal_command_parser.parse(result)
        for cleaner in formatting_mode.rule_cleaners:
            result = cleaner(result)
        return result

    def format(
        self,
        text: str,
        mode: Union[str, FormattingMode] = RAW_MODE,
        use_llm: bool = True,
    ) -> str:
        """Format input text according to mode.

        1. Always runs verbal command parser (if enabled) and offline rule cleaners for the mode.
        2. If mode has a system_prompt, use_llm is True, and an LLM client or API key is available,
           it dispatches to the LLM.
        3. If LLM is unavailable or unconfigured, returns the rule-cleaned output with deterministic
           fallback formatting for common modes (like BULLETS).
        """
        if not text or not text.strip():
            return text

        formatting_mode = self.get_mode(mode)

        # 1. Offline rule-based cleaning (includes verbal command parsing)
        cleaned_text = self.clean_rule_based(text, formatting_mode)

        # If RAW mode or no system prompt, return rule-based result directly
        if formatting_mode.id == "raw" or not formatting_mode.system_prompt:
            return cleaned_text

        # 2. LLM formatting if requested and configured
        if use_llm:
            llm_result = self._call_llm_formatter(
                formatting_mode.system_prompt, cleaned_text
            )
            if llm_result is not None:
                return llm_result

        # 3. Deterministic offline fallback if LLM is disabled or unavailable
        return self._offline_fallback_format(cleaned_text, formatting_mode)

    def _call_llm_formatter(self, system_prompt: str, user_text: str) -> Optional[str]:
        """Attempt to call provided LLM callable or OpenAI client."""
        # OpenAI client if client instance with chat attribute provided or api_key is set
        if (self.llm_client and hasattr(self.llm_client, "chat")) or self.api_key:
            try:
                import openai

                client = (
                    self.llm_client
                    if (self.llm_client and hasattr(self.llm_client, "chat"))
                    else openai.OpenAI(api_key=self.api_key)
                )
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text},
                    ],
                    temperature=0.3,
                )
                if (
                    response
                    and response.choices
                    and response.choices[0].message.content
                ):
                    return response.choices[0].message.content.strip()
            except Exception:
                return None

        # Custom callable LLM client
        if callable(self.llm_client):
            try:
                return self.llm_client(system_prompt, user_text)
            except Exception:
                return None

        return None

    def _offline_fallback_format(self, text: str, mode: FormattingMode) -> str:
        """Deterministic offline fallback for formatted modes when LLM is offline/unconfigured."""
        if mode.id == "bullets":
            # Split sentences into bullet items
            sentences = [s.strip() for s in re.split(r"[.?!]\s+", text) if s.strip()]
            if not sentences:
                return f"- {text}"
            return "\n".join(f"- {s.rstrip('.')}" for s in sentences)

        if mode.id == "meeting_notes":
            return (
                "### Summary\n"
                f"{text}\n\n"
                "### Key Decisions\n"
                "- (Discussed during session)\n\n"
                "### Action Items\n"
                "- [ ] Review transcript notes"
            )

        if mode.id == "email":
            return (
                "Subject: Dictation Update\n\n"
                "Hi there,\n\n"
                f"{text}\n\n"
                "Best regards,\n"
                "[Your Name]"
            )

        if mode.id == "code_comment":
            lines = text.splitlines()
            if len(lines) <= 1:
                return f'"""{text}"""'
            formatted = "\n".join(f"    {line}" for line in lines)
            return f'"""\n{formatted}\n"""'

        if mode.id == "summary":
            sentences = [s.strip() for s in re.split(r"[.?!]\s+", text) if s.strip()]
            if not sentences:
                return f"### Executive Summary\n{text}"
            if len(sentences) <= 2:
                return f"### Executive Summary\n{text}"
            bullet_points = "\n".join(f"- {s.rstrip('.')}" for s in sentences[1:])
            return f"### Executive Summary\n{sentences[0]}.\n\n### Key Takeaways\n{bullet_points}"

        if mode.id in ("translate_en", "custom"):
            return text

        return text
