"""Comprehensive unit tests for Voice Activity Detection (VAD), silence stripper, and audio normalizer.

Verifies:
- Silence trimming (lead-in and lead-out dead silence)
- Speech detection and non-speech rejection (silence, keyboard clatter, breathing, background hiss)
- Volume normalization (standard -16 LUFS / target RMS scaling)
- Empty buffer safety (empty array, zero arrays, NaNs, multi-channel stereo)
- Clipping prevention and soft limiter (no distortion, peak headroom <= 0.98)
- Integration with process_audio and is_speech_present
"""

from pathlib import Path

import numpy as np
import pytest

from scribe_dictation.audio.vad import (
    VADConfig,
    _ensure_mono_float32,
    _soft_limit,
    detect_speech_segments,
    is_speech_present,
    normalize_loudness,
    process_audio,
)


def _generate_sine_wave(
    frequency: float = 440.0,
    duration: float = 1.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> np.ndarray:
    """Generate a clean synthetic sine wave simulating voiced speech."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def _generate_synthetic_speech(
    duration: float = 1.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> np.ndarray:
    """Generate synthetic harmonic audio simulating vowel formants."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Fundamental + formants (F0=200Hz, F1=800Hz, F2=2400Hz)
    signal = (
        0.5 * np.sin(2 * np.pi * 200 * t)
        + 0.3 * np.sin(2 * np.pi * 800 * t)
        + 0.2 * np.sin(2 * np.pi * 2400 * t)
    )
    # Apply envelope to simulate words
    envelope = np.sin(np.pi * np.linspace(0, 1, len(t))) ** 2
    return (amplitude * signal * envelope).astype(np.float32)


class TestEmptyBufferSafety:
    """Tests for empty, zero, invalid, and multi-channel input handling."""

    def test_empty_array(self):
        """Empty input array returns empty output and False for speech."""
        empty = np.array([], dtype=np.float32)
        assert not is_speech_present(empty)
        result = process_audio(empty)
        assert result.size == 0
        assert isinstance(result, np.ndarray)

    def test_zero_length_list(self):
        """Empty list input converts cleanly without error."""
        result = process_audio([])
        assert result.size == 0

    def test_pure_silence(self):
        """All-zero silence buffer is rejected and stripped to empty."""
        silence = np.zeros(16000, dtype=np.float32)
        assert not is_speech_present(silence)
        result = process_audio(silence)
        assert result.size == 0

    def test_stereo_to_mono_conversion(self):
        """2D stereo audio array is converted to 1D mono float32."""
        speech = _generate_synthetic_speech(duration=1.0)
        stereo = np.column_stack([speech, speech])
        mono = _ensure_mono_float32(stereo)
        assert mono.ndim == 1
        assert len(mono) == len(speech)
        assert np.allclose(mono, speech, atol=1e-4)

    def test_integer_pcm_conversion(self):
        """int16 PCM audio is converted to normalized float32 in [-1.0, 1.0]."""
        int16_data = np.array([-32768, 0, 16384, 32767], dtype=np.int16)
        float_data = _ensure_mono_float32(int16_data)
        assert float_data.dtype == np.float32
        assert float_data[0] == -1.0
        assert pytest.approx(float_data[2], 0.01) == 0.5

    def test_nan_and_inf_handling(self):
        """NaNs and Infs are sanitized without crashing."""
        corrupted = np.array([0.0, np.nan, 0.5, np.inf, -np.inf], dtype=np.float32)
        cleaned = _ensure_mono_float32(corrupted)
        assert not np.isnan(cleaned).any()
        assert not np.isinf(cleaned).any()
        assert cleaned[1] == 0.0
        assert cleaned[3] == 1.0
        assert cleaned[4] == -1.0


class TestSpeechDetectionAndNoiseRejection:
    """Tests for detecting speech and rejecting non-speech noise."""

    def test_detects_valid_speech(self):
        """Synthetic speech tone is correctly detected as speech."""
        speech = _generate_synthetic_speech(duration=1.0, sample_rate=16000)
        assert is_speech_present(speech, sample_rate=16000)

    def test_rejects_constant_background_hiss(self):
        """Low-level steady white noise / background hiss is rejected as non-speech."""
        np.random.seed(42)
        hiss = np.random.normal(0, 0.008, 16000).astype(np.float32)
        assert not is_speech_present(hiss, sample_rate=16000)
        processed = process_audio(hiss, sample_rate=16000)
        assert processed.size == 0

    def test_rejects_isolated_keyboard_click(self):
        """Short transient spikes (keyboard clicks, < 30ms) are rejected as non-speech."""
        click = np.zeros(16000, dtype=np.float32)
        # 10ms click impulse
        click[5000:5160] = np.random.uniform(-0.8, 0.8, 160).astype(np.float32)
        config = VADConfig(use_neural_vad=False, min_speech_duration_ms=100)
        assert not is_speech_present(click, sample_rate=16000, config=config)

    def test_rejects_low_frequency_breathing_hum(self):
        """Low amplitude, low frequency hum (< 60Hz) is rejected."""
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        hum = (0.01 * np.sin(2 * np.pi * 30 * t)).astype(np.float32)
        assert not is_speech_present(hum, sample_rate=16000)


class TestSilenceTrimming:
    """Tests for trimming dead lead-in and lead-out silence."""

    def test_trims_leading_and_trailing_silence(self):
        """Lead-in and lead-out silence (1.0s each) is stripped while preserving speech."""
        sample_rate = 16000
        lead_in = np.zeros(sample_rate, dtype=np.float32)  # 1.0s silence
        speech = _generate_synthetic_speech(
            duration=0.8, sample_rate=sample_rate, amplitude=0.6
        )
        lead_out = np.zeros(sample_rate, dtype=np.float32)  # 1.0s silence

        full_audio = np.concatenate([lead_in, speech, lead_out])
        total_len = len(full_audio)

        processed = process_audio(full_audio, sample_rate=sample_rate, pad_ms=150)
        assert processed.size > 0
        # The processed output must be significantly shorter than the un-trimmed full audio
        assert len(processed) < total_len
        # Output should be roughly speech duration + padding (~ 0.8s + 2*0.15s = 1.1s = 17600 samples)
        assert len(processed) < 25000

    def test_detect_speech_segments_boundaries(self):
        """detect_speech_segments identifies speech start and end samples."""
        sample_rate = 16000
        lead_in = np.zeros(sample_rate // 2, dtype=np.float32)  # 0.5s silence
        speech = _generate_synthetic_speech(
            duration=1.0, sample_rate=sample_rate, amplitude=0.5
        )
        lead_out = np.zeros(sample_rate // 2, dtype=np.float32)  # 0.5s silence

        audio = np.concatenate([lead_in, speech, lead_out])
        config = VADConfig(use_neural_vad=False, sample_rate=sample_rate)
        segments = detect_speech_segments(audio, sample_rate=sample_rate, config=config)

        assert len(segments) >= 1
        # Speech starts after lead-in (around sample 8000)
        assert segments[0][0] >= 6000
        # Speech ends before lead-out (around sample 24000)
        assert segments[-1][1] <= 26000


class TestLoudnessNormalizationAndClippingPrevention:
    """Tests for -16 LUFS / target RMS auto-gain and clipping limiter."""

    def test_quiet_speech_boosted_to_target_rms(self):
        """Quiet speech (RMS ~0.02) is boosted towards target RMS (~0.158)."""
        quiet_speech = _generate_synthetic_speech(duration=1.0, amplitude=0.04)
        initial_rms = float(np.sqrt(np.mean(np.square(quiet_speech))))

        normalized = normalize_loudness(
            quiet_speech, target_lufs=-16.0, max_gain_db=24.0
        )
        final_rms = float(np.sqrt(np.mean(np.square(normalized))))

        assert final_rms > initial_rms
        target_rms = 10.0 ** (-16.0 / 20.0)
        assert pytest.approx(final_rms, rel=0.15) == target_rms

    def test_clipping_prevention_on_hot_audio(self):
        """Extremely hot / amplified audio does not clip and stays <= 0.98 peak."""
        hot_audio = _generate_synthetic_speech(duration=1.0, amplitude=3.0)
        assert np.max(np.abs(hot_audio)) > 1.0

        normalized = normalize_loudness(hot_audio, target_lufs=-16.0, target_peak=0.95)
        peak = float(np.max(np.abs(normalized)))

        assert peak <= 0.98
        assert not np.any(np.isnan(normalized))

    def test_soft_limiter_smoothness(self):
        """_soft_limit smoothly compresses peaks exceeding threshold without discontinuity."""
        test_signal = np.array([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0], dtype=np.float32)
        limited = _soft_limit(test_signal, threshold=0.90, hard_limit=0.98)

        assert np.max(np.abs(limited)) <= 0.98
        # Linear region below threshold preserved
        assert limited[2] == -0.5
        assert limited[3] == 0.0
        assert limited[4] == 0.5

    def test_max_gain_db_ceiling_respected(self):
        """Auto-gain respects max_gain_db to prevent excessive noise amplification."""
        very_faint = _generate_synthetic_speech(duration=1.0, amplitude=0.0001)
        normalized = normalize_loudness(very_faint, target_lufs=-16.0, max_gain_db=12.0)

        initial_rms = float(np.sqrt(np.mean(np.square(very_faint))))
        final_rms = float(np.sqrt(np.mean(np.square(normalized))))
        gain_applied = final_rms / (initial_rms + 1e-12)

        max_expected_gain = 10.0 ** (12.0 / 20.0)
        assert gain_applied <= max_expected_gain * 1.05


class TestProcessAudioIntegration:
    """End-to-end integration tests for process_audio pipeline."""

    def test_process_audio_full_pipeline(self):
        """Full pipeline trims silence, normalizes volume, and retains speech fidelity."""
        sample_rate = 16000
        lead_silence = np.zeros(int(sample_rate * 0.8), dtype=np.float32)
        speech = _generate_synthetic_speech(
            duration=1.2, sample_rate=sample_rate, amplitude=0.1
        )
        trail_silence = np.zeros(int(sample_rate * 0.8), dtype=np.float32)

        raw_recording = np.concatenate([lead_silence, speech, trail_silence])
        processed = process_audio(raw_recording, sample_rate=sample_rate)

        assert processed.size > 0
        assert len(processed) < len(raw_recording)
        # Verify speech is present and peak is safe
        assert np.max(np.abs(processed)) <= 0.98
        rms = float(np.sqrt(np.mean(np.square(processed))))
        assert rms > 0.05

    def test_process_audio_on_stereo_pcm(self):
        """process_audio correctly accepts stereo int16 PCM arrays."""
        sample_rate = 16000
        speech = _generate_synthetic_speech(
            duration=1.0, sample_rate=sample_rate, amplitude=0.4
        )
        stereo_int16 = (np.column_stack([speech, speech]) * 32767).astype(np.int16)

        processed = process_audio(stereo_int16, sample_rate=sample_rate)
        assert processed.ndim == 1
        assert processed.dtype == np.float32
        assert processed.size > 0


class TestServicesVADIntegration:
    """Tests verifying VAD integration in AudioRecorder and TranscribeService."""

    def test_audio_recorder_applies_vad_on_stop(self, tmp_path, monkeypatch):
        """AudioRecorder applies VAD when stop() is called."""
        import soundfile as sf
        import scribe_dictation.audio.capture as capture
        from scribe_dictation.audio.capture import AudioRecorder

        monkeypatch.setattr(capture, "DATA_DIR", tmp_path)
        recorder = AudioRecorder(sample_rate=16000, channels=1)
        recorder._is_recording = True

        speech = _generate_synthetic_speech(
            duration=1.0, sample_rate=16000, amplitude=0.3
        )
        # Pad with 1.0s lead and trail silence (skipping the 0.35s chime discard)
        silence = np.zeros(16000, dtype=np.float32)
        full = np.concatenate([silence, speech, silence])
        recorder._recording = [full.reshape(-1, 1)]

        wav_path = recorder.stop(apply_vad=True)
        assert Path(wav_path).exists()
        saved_audio, sr = sf.read(wav_path, dtype="float32")

        # Trimmed audio should be shorter than original raw recording
        assert len(saved_audio) < len(full) - int(0.35 * 16000)
        assert len(saved_audio) > 0

    @pytest.mark.asyncio
    async def test_transcribe_service_skips_silence(self, tmp_path):
        """TranscribeService returns empty string on pure silence without calling Whisper API."""
        import soundfile as sf
        from unittest.mock import AsyncMock
        from scribe_dictation.transcribe.service import TranscribeService

        silent_path = tmp_path / "pure_silence.wav"
        silence = np.zeros(16000 * 2, dtype=np.float32)
        sf.write(str(silent_path), silence, 16000)

        service = TranscribeService(api_key="test-key")
        service._client = AsyncMock()

        result = await service.transcribe(str(silent_path))
        assert result == ""
        # The external API was not called
        service._client.audio.transcriptions.create.assert_not_called()
