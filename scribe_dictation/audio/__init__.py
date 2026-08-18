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
]
