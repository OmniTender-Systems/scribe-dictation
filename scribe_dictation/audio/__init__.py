"""Audio capture and batch transcription modules for scribe-dictation."""

from scribe_dictation.audio.capture import AudioRecorder, record_until_silence
from scribe_dictation.audio.file_transcriber import (
    AudioExtractionError,
    SUPPORTED_EXTENSIONS,
    transcribe_audio_file,
    transcribe_audio_file_async,
)
from scribe_dictation.audio.vad import (
    VADConfig,
    detect_speech_segments,
    is_speech_present,
    normalize_loudness,
    process_audio,
)

from scribe_dictation.audio.sound_bank import (
    DEFAULT_SOUND_THEME,
    FREE_SOUND_THEMES,
    PRO_SOUND_THEMES,
    SETTINGS_SOUND_THEME,
    SOUND_THEMES,
    SoundTheme,
    get_sound_theme,
    get_sound_themes_for_tier,
    get_theme_wav_buffers,
    list_sound_themes,
    play_sound,
    preview_sound,
)

__all__ = [
    "AudioRecorder",
    "record_until_silence",
    "AudioExtractionError",
    "SUPPORTED_EXTENSIONS",
    "transcribe_audio_file",
    "transcribe_audio_file_async",
    "VADConfig",
    "detect_speech_segments",
    "is_speech_present",
    "normalize_loudness",
    "process_audio",
    "SoundTheme",
    "SOUND_THEMES",
    "FREE_SOUND_THEMES",
    "PRO_SOUND_THEMES",
    "DEFAULT_SOUND_THEME",
    "DEFAULT_SOUND_VOLUME",
    "SETTINGS_SOUND_THEME",
    "SETTINGS_SOUND_VOLUME",
    "SETTINGS_PLAY_SOUNDS",
    "get_sound_theme",
    "list_sound_themes",
    "get_sound_themes_for_tier",
    "get_theme_wav_buffers",
    "play_sound",
    "preview_sound",
]
