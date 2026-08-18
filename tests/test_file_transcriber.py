"""Tests for the audio file batch transcriber."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import soundfile as sf

from scribe_dictation.audio.file_transcriber import (
    AudioExtractionError,
    SUPPORTED_EXTENSIONS,
    _chunk_audio_file,
    _load_audio_as_wav,
    transcribe_audio_file,
    transcribe_audio_file_async,
)
from scribe_dictation.export.models import Segment, TranscriptionResult


@pytest.fixture
def sample_wav_file(tmp_path: Path) -> Path:
    """Create a valid 16kHz mono WAV file."""
    wav_path = tmp_path / "sample_recording.wav"
    sample_rate = 16000
    duration = 2.0  # 2 seconds
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
    sf.write(str(wav_path), audio, sample_rate, subtype="PCM_16")
    return wav_path


@pytest.fixture
def sample_stereo_wav_file(tmp_path: Path) -> Path:
    """Create a stereo WAV file."""
    wav_path = tmp_path / "stereo_recording.wav"
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    left = 0.5 * np.sin(2 * np.pi * 440 * t)
    right = 0.5 * np.cos(2 * np.pi * 440 * t)
    stereo = np.column_stack([left, right])
    sf.write(str(wav_path), stereo, sample_rate, subtype="PCM_16")
    return wav_path


class TestFileTranscriberFormatsAndValidation:
    """Tests for file validation and format handling."""

    def test_supported_extensions(self):
        """Verify standard media formats are supported."""
        assert ".mp3" in SUPPORTED_EXTENSIONS
        assert ".wav" in SUPPORTED_EXTENSIONS
        assert ".m4a" in SUPPORTED_EXTENSIONS
        assert ".ogg" in SUPPORTED_EXTENSIONS
        assert ".flac" in SUPPORTED_EXTENSIONS
        assert ".mp4" in SUPPORTED_EXTENSIONS

    def test_nonexistent_file_raises(self, tmp_path: Path):
        """Non-existent file raises FileNotFoundError."""
        mock_transcriber = MagicMock()
        non_existent = tmp_path / "missing.wav"
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            transcribe_audio_file(non_existent, mock_transcriber)

    def test_unsupported_format_raises(self, tmp_path: Path):
        """Unsupported format raises ValueError."""
        mock_transcriber = MagicMock()
        bad_file = tmp_path / "video.avi"
        bad_file.write_bytes(b"dummy")
        with pytest.raises(ValueError, match="Unsupported file format"):
            transcribe_audio_file(bad_file, mock_transcriber)


class TestAudioLoadingAndChunking:
    """Tests for audio loading and chunking."""

    def test_load_wav_direct(self, sample_wav_file: Path, tmp_path: Path):
        """Loading a 16kHz mono WAV extracts valid audio file."""
        extracted = _load_audio_as_wav(sample_wav_file, tmp_path)
        assert extracted.exists()
        info = sf.info(str(extracted))
        assert info.samplerate == 16000
        assert info.channels == 1

    def test_chunking_short_audio(self, sample_wav_file: Path, tmp_path: Path):
        """Audio shorter than chunk duration returns 1 chunk."""
        chunks = _chunk_audio_file(sample_wav_file, tmp_path, chunk_duration=10.0)
        assert len(chunks) == 1
        assert chunks[0][1] == 0.0  # offset

    def test_chunking_long_audio(self, sample_wav_file: Path, tmp_path: Path):
        """Audio longer than chunk duration is split into multiple chunks."""
        # 2.0s audio chunked at 0.75s should produce 3 chunks (0.75, 0.75, 0.5)
        chunks = _chunk_audio_file(sample_wav_file, tmp_path, chunk_duration=0.75)
        assert len(chunks) == 3
        assert chunks[0][1] == 0.0
        assert pytest.approx(chunks[1][1], 0.01) == 0.75
        assert pytest.approx(chunks[2][1], 0.01) == 1.5


class TestTranscriptionExecution:
    """Tests for transcription execution with various transcriber engines."""

    @pytest.mark.asyncio
    async def test_transcribe_with_callable(self, sample_wav_file: Path):
        """Transcribing with a direct async/sync callable."""

        def mock_transcriber_func(audio_path: str):
            return "This is test transcript from callable."

        result = await transcribe_audio_file_async(
            sample_wav_file, mock_transcriber_func
        )
        assert isinstance(result, TranscriptionResult)
        assert result.title == "sample_recording"
        assert result.text == "This is test transcript from callable."
        assert len(result.segments) == 1
        assert result.segments[0].start == 0.0

    @pytest.mark.asyncio
    async def test_transcribe_with_service_object(self, sample_wav_file: Path):
        """Transcribing with a TranscribeService-like mock with async transcribe()."""
        service = MagicMock()
        service.transcribe = AsyncMock(return_value="Service transcript output.")

        progress_calls = []

        def on_progress(p: float):
            progress_calls.append(p)

        result = await transcribe_audio_file_async(
            sample_wav_file, service, progress_callback=on_progress
        )

        assert result.text == "Service transcript output."
        assert 0.0 in progress_calls
        assert 1.0 in progress_calls

    @pytest.mark.asyncio
    async def test_transcribe_with_segments_method(self, sample_wav_file: Path):
        """Transcriber returning explicit Segment list."""
        service = MagicMock()
        service.transcribe_segments = MagicMock(
            return_value=[
                Segment(start=0.0, end=1.0, text="First part."),
                Segment(start=1.0, end=2.0, text="Second part."),
            ]
        )

        result = await transcribe_audio_file_async(sample_wav_file, service)
        assert len(result.segments) == 2
        assert result.segments[0].text == "First part."
        assert result.segments[1].text == "Second part."
        assert result.text == "First part. Second part."

    @pytest.mark.asyncio
    async def test_transcribe_with_faster_whisper_local_model(
        self, sample_wav_file: Path
    ):
        """Transcribing with faster_whisper-style local model."""
        service = MagicMock()
        service.use_local = True

        seg1 = MagicMock()
        seg1.start = 0.0
        seg1.end = 1.0
        seg1.text = " Local faster-whisper text. "

        seg2 = MagicMock()
        seg2.start = 1.0
        seg2.end = 2.0
        seg2.text = " Second segment. "

        local_model = MagicMock()
        local_model.transcribe.return_value = ([seg1, seg2], MagicMock())
        service._local_model = local_model

        result = await transcribe_audio_file_async(sample_wav_file, service)
        assert len(result.segments) == 2
        assert result.segments[0].text == "Local faster-whisper text."
        assert result.segments[1].text == "Second segment."

    def test_sync_transcribe_audio_file_entrypoint(self, sample_wav_file: Path):
        """Synchronous transcribe_audio_file helper returns TranscriptionResult."""
        service = MagicMock()
        service.transcribe = AsyncMock(return_value="Synchronous execution test.")

        result = transcribe_audio_file(sample_wav_file, service)
        assert isinstance(result, TranscriptionResult)
        assert result.text == "Synchronous execution test."

    def test_ffmpeg_missing_raises_audio_extraction_error(self, tmp_path: Path):
        """When ffmpeg is missing and required, raises AudioExtractionError."""
        dummy_mp3 = tmp_path / "test.mp3"
        dummy_mp3.write_bytes(b"ID3dummy")

        with patch("shutil.which", return_value=None):
            with pytest.raises(
                AudioExtractionError, match="ffmpeg executable not found"
            ):
                _load_audio_as_wav(dummy_mp3, tmp_path)
