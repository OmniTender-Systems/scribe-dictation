"""Supported languages and translation configurations for Privacy Scribe.

Provides:
- SupportedLanguage dataclass
- SUPPORTED_LANGUAGES dictionary and list
- Helper functions for resolving language codes and display labels
- Task constants: "transcribe" vs "translate"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


TASK_TRANSCRIBE = "transcribe"
TASK_TRANSLATE = "translate"
SUPPORTED_TASKS = [TASK_TRANSCRIBE, TASK_TRANSLATE]


@dataclass(frozen=True)
class SupportedLanguage:
    """Language representation with code, names, and flag emoji."""

    code: str
    name: str
    native_name: str
    flag: str

    @property
    def display_name(self) -> str:
        """User-friendly display label with flag and name."""
        if self.native_name and self.native_name.lower() != self.name.lower():
            return f"{self.flag} {self.name} ({self.native_name})"
        return f"{self.flag} {self.name}"


# Auto-detect pseudo language
AUTO_LANGUAGE = SupportedLanguage(
    code="auto",
    name="Auto-Detect Language",
    native_name="Auto",
    flag="🌐",
)

# Comprehensive list of popular / supported Whisper languages
LANGUAGES: list[SupportedLanguage] = [
    AUTO_LANGUAGE,
    SupportedLanguage(code="en", name="English", native_name="English", flag="🇺🇸"),
    SupportedLanguage(code="es", name="Spanish", native_name="Español", flag="🇪🇸"),
    SupportedLanguage(code="fr", name="French", native_name="Français", flag="🇫🇷"),
    SupportedLanguage(code="de", name="German", native_name="Deutsch", flag="🇩🇪"),
    SupportedLanguage(code="zh", name="Chinese", native_name="中文", flag="🇨🇳"),
    SupportedLanguage(code="ja", name="Japanese", native_name="日本語", flag="🇯🇵"),
    SupportedLanguage(code="ko", name="Korean", native_name="한국어", flag="🇰🇷"),
    SupportedLanguage(code="it", name="Italian", native_name="Italiano", flag="🇮🇹"),
    SupportedLanguage(code="pt", name="Portuguese", native_name="Português", flag="🇧🇷"),
    SupportedLanguage(code="ru", name="Russian", native_name="Русский", flag="🇷🇺"),
    SupportedLanguage(code="ar", name="Arabic", native_name="العربية", flag="🇸🇦"),
    SupportedLanguage(code="hi", name="Hindi", native_name="हिन्दी", flag="🇮🇳"),
    SupportedLanguage(code="nl", name="Dutch", native_name="Nederlands", flag="🇳🇱"),
    SupportedLanguage(code="pl", name="Polish", native_name="Polski", flag="🇵🇱"),
    SupportedLanguage(code="tr", name="Turkish", native_name="Türkçe", flag="🇹🇷"),
    SupportedLanguage(code="uk", name="Ukrainian", native_name="Українська", flag="🇺🇦"),
    SupportedLanguage(
        code="vi", name="Vietnamese", native_name="Tiếng Việt", flag="🇻🇳"
    ),
    SupportedLanguage(
        code="id", name="Indonesian", native_name="Bahasa Indonesia", flag="🇮🇩"
    ),
    SupportedLanguage(code="sv", name="Swedish", native_name="Svenska", flag="🇸🇪"),
    SupportedLanguage(code="el", name="Greek", native_name="Ελληνικά", flag="🇬🇷"),
    SupportedLanguage(code="cs", name="Czech", native_name="Čeština", flag="🇨🇿"),
    SupportedLanguage(code="da", name="Danish", native_name="Dansk", flag="🇩🇰"),
    SupportedLanguage(code="fi", name="Finnish", native_name="Suomi", flag="🇫🇮"),
    SupportedLanguage(code="he", name="Hebrew", native_name="עברית", flag="🇮🇱"),
    SupportedLanguage(code="hu", name="Hungarian", native_name="Magyar", flag="🇭🇺"),
    SupportedLanguage(code="no", name="Norwegian", native_name="Norsk", flag="🇳🇴"),
    SupportedLanguage(code="ro", name="Romanian", native_name="Română", flag="🇷🇴"),
    SupportedLanguage(code="th", name="Thai", native_name="ไทย", flag="🇹🇭"),
    SupportedLanguage(code="tl", name="Tagalog", native_name="Tagalog", flag="🇵🇭"),
]

SUPPORTED_LANGUAGES: dict[str, SupportedLanguage] = {
    lang.code: lang for lang in LANGUAGES
}


def get_language_by_code(code: Optional[str]) -> SupportedLanguage:
    """Retrieve language metadata by ISO code, defaulting to Auto."""
    if not code:
        return AUTO_LANGUAGE
    clean_code = code.lower().strip()
    return SUPPORTED_LANGUAGES.get(clean_code, AUTO_LANGUAGE)


def normalize_language_param(language: Optional[str]) -> Optional[str]:
    """Normalize language code for backend whisper engines.

    Returns None when 'auto', or the lowercased ISO code.
    """
    if not language or language.lower().strip() in ("auto", "none", ""):
        return None
    return language.lower().strip()


def normalize_task_param(task: Optional[str]) -> str:
    """Normalize transcription task parameter ('transcribe' or 'translate')."""
    if not task:
        return TASK_TRANSCRIBE
    t = task.lower().strip()
    return TASK_TRANSLATE if t in ("translate", "translation") else TASK_TRANSCRIBE
