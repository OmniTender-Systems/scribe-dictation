"""Transcription service module for scribe-dictation."""

from scribe_dictation.transcribe.languages import (
    AUTO_LANGUAGE,
    LANGUAGES,
    SUPPORTED_LANGUAGES,
    TASK_TRANSCRIBE,
    TASK_TRANSLATE,
    SupportedLanguage,
    get_language_by_code,
    normalize_language_param,
    normalize_task_param,
)
from scribe_dictation.transcribe.local import LocalWhisperService
from scribe_dictation.transcribe.service import (
    FALLBACK_MESSAGE,
    MAX_RETRIES,
    TranscribeService,
    TranscriptionError,
)
from scribe_dictation.transcribe.vocabulary import (
    CustomVocabularyManager,
    ReplacementRule,
    apply_replacements,
    build_initial_prompt,
    get_default_config_path,
)

__all__ = [
    "TranscribeService",
    "TranscriptionError",
    "LocalWhisperService",
    "CustomVocabularyManager",
    "ReplacementRule",
    "build_initial_prompt",
    "apply_replacements",
    "get_default_config_path",
    "FALLBACK_MESSAGE",
    "MAX_RETRIES",
    "SupportedLanguage",
    "AUTO_LANGUAGE",
    "LANGUAGES",
    "SUPPORTED_LANGUAGES",
    "TASK_TRANSCRIBE",
    "TASK_TRANSLATE",
    "get_language_by_code",
    "normalize_language_param",
    "normalize_task_param",
]
