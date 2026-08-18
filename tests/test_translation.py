"""Unit tests for multi-language auto-detection and speech-to-English translation."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scribe_dictation.transcribe.languages import (
    LANGUAGES,
    SUPPORTED_LANGUAGES,
    TASK_TRANSCRIBE,
    TASK_TRANSLATE,
    get_language_by_code,
    normalize_language_param,
    normalize_task_param,
)
from scribe_dictation.transcribe.local import LocalWhisperService
from scribe_dictation.transcribe.service import TranscribeService


@pytest.fixture
def mock_wav_file(tmp_path: Path) -> str:
    """Create a mock WAV file."""
    wav = tmp_path / "sample_speech.wav"
    wav.write_bytes(b"RIFF....WAVE....fake_audio_data")
    return str(wav)


class TestLanguagesConstantsAndHelpers:
    """Tests for language dictionaries and resolution utilities."""

    def test_languages_definition(self):
        """Verify core languages exist in LANGUAGES and SUPPORTED_LANGUAGES."""
        assert len(LANGUAGES) >= 20
        assert "auto" in SUPPORTED_LANGUAGES
        assert "es" in SUPPORTED_LANGUAGES
        assert "fr" in SUPPORTED_LANGUAGES
        assert "de" in SUPPORTED_LANGUAGES
        assert "zh" in SUPPORTED_LANGUAGES
        assert "ja" in SUPPORTED_LANGUAGES

    def test_supported_language_display_name(self):
        """Display name includes flag, English name, and native name."""
        lang_es = SUPPORTED_LANGUAGES["es"]
        assert "🇪🇸" in lang_es.display_name
        assert "Spanish" in lang_es.display_name
        assert "Español" in lang_es.display_name

        lang_en = SUPPORTED_LANGUAGES["en"]
        assert "🇺🇸" in lang_en.display_name
        assert "English" in lang_en.display_name

    def test_get_language_by_code(self):
        """Lookup by code is case-insensitive and falls back to Auto."""
        assert get_language_by_code("ES").code == "es"
        assert get_language_by_code("fr ").code == "fr"
        assert get_language_by_code(None).code == "auto"
        assert get_language_by_code("unknown_code").code == "auto"

    def test_normalize_language_param(self):
        """Normalization returns ISO code or None for auto."""
        assert normalize_language_param("auto") is None
        assert normalize_language_param("Auto") is None
        assert normalize_language_param(None) is None
        assert normalize_language_param("") is None
        assert normalize_language_param("FR") == "fr"
        assert normalize_language_param("  de  ") == "de"

    def test_normalize_task_param(self):
        """Normalization maps translate variations to TASK_TRANSLATE, otherwise TASK_TRANSCRIBE."""
        assert normalize_task_param("translate") == TASK_TRANSLATE
        assert normalize_task_param("TRANSLATE") == TASK_TRANSLATE
        assert normalize_task_param("translation") == TASK_TRANSLATE
        assert normalize_task_param("transcribe") == TASK_TRANSCRIBE
        assert normalize_task_param(None) == TASK_TRANSCRIBE
        assert normalize_task_param("other") == TASK_TRANSCRIBE


class TestOpenAITranscribeAndTranslateService:
    """Tests for OpenAI Whisper API transcribe vs translate modes."""

    @pytest.mark.asyncio
    async def test_openai_transcribe_default_auto(self, mock_wav_file):
        """Default transcribe mode calls audio.transcriptions.create without language if auto."""
        mock_response = MagicMock()
        mock_response.text = "Bonjour le monde"

        service = TranscribeService(
            api_key="sk-test", use_local=False, language="auto", task="transcribe"
        )
        service._client = AsyncMock()
        service._client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        result = await service.transcribe(mock_wav_file)
        assert result == "Bonjour le monde"

        service._client.audio.transcriptions.create.assert_called_once()
        kwargs = service._client.audio.transcriptions.create.call_args.kwargs
        assert kwargs["model"] == "whisper-1"
        assert "language" not in kwargs

    @pytest.mark.asyncio
    async def test_openai_transcribe_with_specific_language(self, mock_wav_file):
        """Specifying a language passes the language parameter to audio.transcriptions.create."""
        mock_response = MagicMock()
        mock_response.text = "Hola mundo"

        service = TranscribeService(api_key="sk-test", use_local=False, language="es")
        service._client = AsyncMock()
        service._client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        result = await service.transcribe(mock_wav_file)
        assert result == "Hola mundo"

        kwargs = service._client.audio.transcriptions.create.call_args.kwargs
        assert kwargs["language"] == "es"

    @pytest.mark.asyncio
    async def test_openai_translate_to_english(self, mock_wav_file):
        """Task='translate' invokes audio.translations.create endpoint."""
        mock_response = MagicMock()
        mock_response.text = "Hello world"

        service = TranscribeService(
            api_key="sk-test", use_local=False, task="translate"
        )
        service._client = AsyncMock()
        service._client.audio.translations.create = AsyncMock(
            return_value=mock_response
        )
        service._client.audio.transcriptions.create = AsyncMock()

        result = await service.transcribe(mock_wav_file)
        assert result == "Hello world"

        service._client.audio.translations.create.assert_called_once()
        service._client.audio.transcriptions.create.assert_not_called()
        kwargs = service._client.audio.translations.create.call_args.kwargs
        assert kwargs["model"] == "whisper-1"

    @pytest.mark.asyncio
    async def test_openai_override_language_and_task(self, mock_wav_file):
        """Method-level parameters override instance defaults."""
        mock_trans_resp = MagicMock(text="Translated to English")
        service = TranscribeService(
            api_key="sk-test", use_local=False, language="es", task="transcribe"
        )
        service._client = AsyncMock()
        service._client.audio.translations.create = AsyncMock(
            return_value=mock_trans_resp
        )

        result = await service.transcribe(mock_wav_file, task="translate")
        assert result == "Translated to English"
        service._client.audio.translations.create.assert_called_once()


class TestLocalWhisperServiceTranslation:
    """Tests for local faster-whisper service language and task options."""

    def test_local_whisper_transcribe_params(self, mock_wav_file):
        """Local service passes language and task to faster-whisper model.transcribe."""
        service = LocalWhisperService(language="de", task="transcribe")
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Guten Tag"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        service._model = mock_model

        result = service.transcribe(mock_wav_file)
        assert result == "Guten Tag"

        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args.kwargs
        assert call_kwargs["language"] == "de"
        assert call_kwargs["task"] == "transcribe"

    def test_local_whisper_translate_params(self, mock_wav_file):
        """Local service passes task='translate' to model.transcribe."""
        service = LocalWhisperService(language="ja", task="translate")
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Good afternoon"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        service._model = mock_model

        result = service.transcribe(mock_wav_file)
        assert result == "Good afternoon"

        call_kwargs = mock_model.transcribe.call_args.kwargs
        assert call_kwargs["language"] == "ja"
        assert call_kwargs["task"] == "translate"

    def test_local_whisper_auto_language_omits_language_param(self, mock_wav_file):
        """Auto language does not pass a language argument, enabling auto-detection."""
        service = LocalWhisperService(language="auto", task="transcribe")
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Auto detected speech"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        service._model = mock_model

        result = service.transcribe(mock_wav_file)
        assert result == "Auto detected speech"

        call_kwargs = mock_model.transcribe.call_args.kwargs
        assert "language" not in call_kwargs

    def test_local_whisper_transcribe_segments(self, mock_wav_file):
        """transcribe_segments honors language and translation task."""
        service = LocalWhisperService(language="es", task="translate")
        mock_model = MagicMock()
        mock_seg = MagicMock(start=0.0, end=1.5, text="Hello friend")
        mock_model.transcribe.return_value = ([mock_seg], MagicMock())
        service._model = mock_model

        segments = service.transcribe_segments(mock_wav_file)
        assert len(segments) == 1
        assert segments[0].text == "Hello friend"
        assert segments[0].start == 0.0
        assert segments[0].end == 1.5

        call_kwargs = mock_model.transcribe.call_args.kwargs
        assert call_kwargs["language"] == "es"
        assert call_kwargs["task"] == "translate"

    @pytest.mark.asyncio
    async def test_transcribe_service_local_delegation(self, mock_wav_file):
        """TranscribeService with use_local=True delegates language and task parameters."""
        service = TranscribeService(use_local=True, language="fr", task="translate")
        mock_local = MagicMock()
        mock_local.transcribe_async = AsyncMock(
            return_value="English translation from French"
        )
        service._local_service = mock_local

        result = await service.transcribe(mock_wav_file)
        assert result == "English translation from French"
        mock_local.transcribe_async.assert_called_once_with(
            mock_wav_file,
            initial_prompt=None,
            language="fr",
            task="translate",
        )


class TestSettingsDialogLanguageGating:
    """Tests that Free Edition gates Auto-Detect and Translation while allowing explicit language selection."""

    def test_free_edition_language_badges(self, monkeypatch):
        """Free Edition shows Pro Lifetime Only badges for Auto-Detect and Translation."""
        import sys
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from scribe_dictation.ui.app import (
            SettingsDialog,
            SETTINGS_LANGUAGE,
            SETTINGS_TASK,
        )

        _app = QApplication.instance() or QApplication(sys.argv)
        monkeypatch.setattr(
            "scribe_dictation.ui.app.is_offline_cache_valid", lambda: False
        )
        settings = QSettings("ScribeDictationTest", "LangTest")
        settings.clear()

        dialog = SettingsDialog(None)

        # Verify auto-detect item text contains Pro Lifetime Only
        auto_idx = dialog.language_combo.findData("auto")
        assert auto_idx >= 0
        assert "Pro Lifetime Only" in dialog.language_combo.itemText(auto_idx)

        # Verify translation item text contains Pro Lifetime Only
        trans_idx = dialog.task_combo.findData(TASK_TRANSLATE)
        assert trans_idx >= 0
        assert "Pro Lifetime Only" in dialog.task_combo.itemText(trans_idx)

        # Explicit language selection works
        es_idx = dialog.language_combo.findData("es")
        assert es_idx >= 0
        dialog.language_combo.setCurrentIndex(es_idx)

        with patch("PySide6.QtWidgets.QMessageBox.information"):
            dialog._save()

        assert dialog.settings.value(SETTINGS_LANGUAGE) == "es"
        assert dialog.settings.value(SETTINGS_TASK) == TASK_TRANSCRIBE
        settings.clear()

    def test_free_edition_auto_detect_fallback(self, monkeypatch):
        """Selecting Auto-Detect on Free Edition alerts user and falls back to 'en'."""
        import sys
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from scribe_dictation.ui.app import SettingsDialog, SETTINGS_LANGUAGE

        _app = QApplication.instance() or QApplication(sys.argv)
        monkeypatch.setattr(
            "scribe_dictation.ui.app.is_offline_cache_valid", lambda: False
        )
        settings = QSettings("ScribeDictationTest", "LangTest2")
        settings.clear()

        dialog = SettingsDialog(None)
        auto_idx = dialog.language_combo.findData("auto")
        dialog.language_combo.setCurrentIndex(auto_idx)

        with patch("PySide6.QtWidgets.QMessageBox.information") as mock_box:
            dialog._save()
            mock_box.assert_called_once()

        assert dialog.settings.value(SETTINGS_LANGUAGE) == "en"
        settings.clear()
