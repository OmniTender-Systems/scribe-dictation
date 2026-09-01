"""Transcription service supporting both OpenAI Whisper API and local faster-whisper.

Provides:
- TranscribeService: async transcription of WAV files
- Automatic retry (2 attempts) on API errors (for online mode)
- Configurable model, local model size, device, API key, and CustomVocabularyManager biasing
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
import soundfile as sf

from scribe_dictation.audio.vad import is_speech_present
from scribe_dictation.transcribe.local import LocalWhisperService
from scribe_dictation.transcribe.vocabulary import CustomVocabularyManager

from scribe_dictation.transcribe.voice_profile import VoiceProfile

DEFAULT_MODEL = "whisper-1"
DEFAULT_LOCAL_MODEL = "base"
MAX_RETRIES = 2
FALLBACK_MESSAGE = (
    "[Transcription failed. Please check your configuration and try again.]"
)


class TranscriptionError(Exception):
    """Raised when transcription fails."""


class TranscribeService:
    """Service for transcribing audio files using OpenAI's Whisper API or local faster-whisper."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        use_local: bool = False,
        local_model_size: str = DEFAULT_LOCAL_MODEL,
        local_device: str = "auto",
        local_compute_type: str = "default",
        vocabulary_manager: Optional[CustomVocabularyManager] = None,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None,
        task: str = "transcribe",
        voice_profile: Optional[VoiceProfile] = None,
    ):
        self.use_local = use_local
        self.model = model
        self.local_model_size = local_model_size
        self.local_device = local_device
        self.local_compute_type = local_compute_type
        self.vocabulary_manager = vocabulary_manager
        self.initial_prompt = initial_prompt
        self.language = language
        self.task = task
        self.voice_profile = voice_profile

        self._local_service: Optional[LocalWhisperService] = None
        if self.use_local:
            self._local_service = LocalWhisperService(
                model_size=self.local_model_size,
                device=self.local_device,
                compute_type=self.local_compute_type,
                vocabulary_manager=self.vocabulary_manager,
                initial_prompt=self.initial_prompt,
                language=self.language,
                task=self.task,
            )
        else:
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            if not self.api_key:
                raise ValueError(
                    "OpenAI API key is required. Set OPENAI_API_KEY environment "
                    "variable or pass api_key to TranscribeService."
                )
            self._client = AsyncOpenAI(api_key=self.api_key)

    @property
    def _local_model(self):
        """Access the underlying faster-whisper model for backward compatibility."""
        if self._local_service is not None:
            return self._local_service._model
        return None

    @_local_model.setter
    def _local_model(self, model):
        if self._local_service is not None:
            self._local_service._model = model

    def _init_local_model(self):
        """Lazy load the local faster-whisper model."""
        if self._local_service is None:
            self._local_service = LocalWhisperService(
                model_size=self.local_model_size,
                device=self.local_device,
                compute_type=self.local_compute_type,
                vocabulary_manager=self.vocabulary_manager,
                initial_prompt=self.initial_prompt,
                language=self.language,
                task=self.task,
            )
        self._local_service._init_model()

    def _get_initial_prompt(self, extra_prompt: Optional[str] = None) -> Optional[str]:
        """Compute the combined initial_prompt for OpenAI API or local transcription."""
        base = extra_prompt if extra_prompt is not None else self.initial_prompt
        if self.vocabulary_manager is not None:
            prompt = self.vocabulary_manager.build_initial_prompt(base_prompt=base)
            return prompt if prompt else None
        return base if base else None

    async def transcribe(
        self,
        audio_path: str,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None,
        task: Optional[str] = None,
    ) -> str:
        """Transcribe or translate a WAV audio file.

        Args:
            audio_path: Path to a WAV file.
            initial_prompt: Optional prompt override for vocabulary biasing.
            language: Optional language code (e.g., 'es', 'fr', 'auto') overriding instance setting.
            task: Optional task ('transcribe' or 'translate') overriding instance setting.

        Returns:
            Transcribed or translated text.

        Raises:
            TranscriptionError: If transcription fails.
        """
        path = Path(audio_path)
        if not path.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        # VAD check: if audio file contains no speech / pure silence, return empty string
        # to avoid silence hallucinations (e.g. '[Music]', 'Thank you for watching')
        try:
            audio_arr, sr = sf.read(str(path), dtype="float32")
            if audio_arr.size == 0 or not is_speech_present(audio_arr, sample_rate=sr):
                return ""
        except Exception:
            # If audio cannot be decoded with soundfile (e.g. mock test payload), proceed as-is
            pass

        target_lang = language if language is not None else self.language
        target_task = task if task is not None else self.task
        normalized_task = (
            "translate"
            if target_task
            and target_task.lower().strip() in ("translate", "translation")
            else "transcribe"
        )

        effective_prompt = (
            self.voice_profile.bias_prompt() if self.voice_profile else initial_prompt
        )

        if self.use_local:
            try:
                if self._local_service is None:
                    self._init_local_model()
                res = await self._local_service.transcribe_async(
                    audio_path,
                    initial_prompt=effective_prompt,
                    language=target_lang,
                    task=normalized_task,
                )
                if self.voice_profile and res:
                    self.voice_profile.observe(res)
                return res
            except Exception as e:
                print(f"Local transcription failed: {e}")
                return f"[Local transcription failed: {e}]"

        # Online API mode
        prompt = self._get_initial_prompt(effective_prompt)
        last_error: Optional[Exception] = None

        for attempt in range(
            1, MAX_RETRIES + 2
        ):  # 3 attempts total (initial + 2 retries)
            try:
                with open(audio_path, "rb") as audio_file:
                    create_kwargs = {
                        "model": self.model,
                        "file": audio_file,
                    }
                    if prompt:
                        create_kwargs["prompt"] = prompt

                    if normalized_task == "translate":
                        # OpenAI Translations API: client.audio.translations.create
                        # Note: OpenAI translations endpoint translates directly to English
                        transcript = await self._client.audio.translations.create(
                            **create_kwargs
                        )
                    else:
                        # OpenAI Transcriptions API: client.audio.transcriptions.create
                        if target_lang and target_lang.lower().strip() not in (
                            "auto",
                            "none",
                            "",
                        ):
                            create_kwargs["language"] = target_lang.lower().strip()
                        transcript = await self._client.audio.transcriptions.create(
                            **create_kwargs
                        )

                text = transcript.text
                if self.vocabulary_manager is not None:
                    text = self.vocabulary_manager.apply_replacements(text)
                if self.voice_profile and text:
                    self.voice_profile.observe(text)
                return text

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES + 1:
                    continue
                break

        error_msg = str(last_error) if last_error else "Unknown error"
        print(f"Transcription failed after {MAX_RETRIES + 1} attempts: {error_msg}")
        return FALLBACK_MESSAGE

    async def transcribe_text(self, text: str) -> str:
        """Synchronous-like convenience: returns the input text with vocabulary replacements applied."""
        if self.vocabulary_manager is not None:
            return self.vocabulary_manager.apply_replacements(text)
        return text
