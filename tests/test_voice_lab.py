"""Tests for Voice Lab Calibration Runner and Diff Learner Engine."""

import numpy as np
import pytest

from scribe_dictation.transcribe.vocabulary import CustomVocabularyManager
from scribe_dictation.tuning.diff_learner import DiffLearner, DiffSuggestion
from scribe_dictation.tuning.voice_lab import (
    CalibrationResult,
    CalibrationSentence,
    VoiceCalibrationRunner,
)


class TestVoiceLab:
    """Test suite for voice calibration metrics and sentence evaluation."""

    def test_calibration_sentences_structure(self):
        sentences = VoiceCalibrationRunner.get_sentences()
        assert len(sentences) >= 6
        assert all(isinstance(s, CalibrationSentence) for s in sentences)
        for s in sentences:
            assert s.id
            assert s.text
            assert s.word_count > 0
            assert s.target_category
            assert s.target_phonemes

    def test_analyze_empty_audio(self):
        runner = VoiceCalibrationRunner()
        result = runner.analyze_audio(np.array([]))
        assert isinstance(result, CalibrationResult)
        assert result.duration_seconds == 0.0
        assert result.quality_grade == "Poor"
        assert result.wpm == 0.0

    def test_analyze_synthetic_speech_signal(self):
        runner = VoiceCalibrationRunner()
        sample_rate = 16000
        duration = 3.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

        # Generate carrier speech bursts with natural silent pauses
        # 1.5s speech bursts at 300Hz, 1.5s background silence
        speech_envelope = (np.sin(2 * np.pi * 1.5 * t) > 0).astype(np.float32)
        signal = 0.4 * np.sin(2 * np.pi * 300 * t) * speech_envelope
        # Add slight background noise (SNR ~ 20-30dB)
        noise = 0.005 * np.random.normal(size=len(t))
        audio = (signal + noise).astype(np.float32)

        result = runner.analyze_audio(
            audio_data=audio,
            sample_rate=sample_rate,
            expected_word_count=10,
        )

        assert result.duration_seconds == pytest.approx(3.0, abs=0.1)
        assert result.spoken_word_count == 10
        assert result.wpm == pytest.approx(200.0, abs=10.0)
        assert result.peak_amplitude > 0.3
        assert result.snr_db > 10.0
        assert result.quality_grade in ("Good", "Excellent")
        assert 0.005 <= result.recommended_silence_threshold <= 0.08
        assert 1.0 <= result.recommended_silence_duration <= 2.0

    def test_analyze_loud_clipping_audio(self):
        runner = VoiceCalibrationRunner()
        # Full clipping signal
        audio = np.ones(16000, dtype=np.float32)
        result = runner.analyze_audio(audio, sample_rate=16000, expected_word_count=5)
        assert result.peak_amplitude == 1.0
        assert any("clipping" in note.lower() for note in result.feedback_notes)

    def test_calibration_result_serialization(self):
        res = CalibrationResult(
            duration_seconds=2.5,
            spoken_word_count=8,
            wpm=192.0,
            average_rms=0.25,
            peak_amplitude=0.72,
            noise_floor_rms=0.01,
            snr_db=28.0,
            recommended_silence_threshold=0.02,
            recommended_silence_duration=1.2,
            recommended_gain_factor=1.04,
            quality_grade="Excellent",
            feedback_notes=["Test note"],
        )
        d = res.to_dict()
        restored = CalibrationResult.from_dict(d)
        assert restored.wpm == 192.0
        assert restored.quality_grade == "Excellent"
        assert restored.feedback_notes == ["Test note"]


class TestDiffLearner:
    """Test suite for continuous learning diff engine."""

    def test_extract_replacements_exact_words(self):
        learner = DiffLearner()
        orig = "I am deploying on Next JS and Postgre SQL today."
        edited = "I am deploying on Next.js and PostgreSQL today."

        suggestions = learner.extract_replacements(orig, edited)
        assert len(suggestions) >= 2

        replacements_map = {s.original: s.replacement for s in suggestions}
        assert "Next JS" in replacements_map or "Next" in replacements_map
        assert (
            replacements_map.get("Next JS") == "Next.js"
            or "Next.js" in replacements_map.values()
        )

    def test_extract_replacements_tech_acronym(self):
        learner = DiffLearner()
        orig = "Run kube cuddle get pods in the cluster."
        edited = "Run kubectl get pods in the cluster."

        suggestions = learner.extract_replacements(orig, edited)
        assert len(suggestions) == 1
        assert suggestions[0].original == "kube cuddle"
        assert suggestions[0].replacement == "kubectl"

    def test_extract_no_changes(self):
        learner = DiffLearner()
        suggestions = learner.extract_replacements(
            "Identical text string.", "Identical text string."
        )
        assert suggestions == []

    def test_apply_suggestions_to_vocabulary_manager(self, tmp_path):
        config_file = tmp_path / "vocab.json"
        manager = CustomVocabularyManager(config_path=config_file, auto_load=False)
        learner = DiffLearner()

        suggestions = [
            DiffSuggestion(
                original="kube cuddle", replacement="kubectl", confidence=0.9
            ),
            DiffSuggestion(
                original="pie side six", replacement="PySide6", confidence=0.85
            ),
        ]

        added_rules = learner.apply_to_vocabulary(
            suggestions, manager, min_confidence=0.7
        )
        assert len(added_rules) == 2
        assert (
            manager.apply_replacements("Please run kube cuddle now")
            == "Please run kubectl now"
        )
        assert manager.apply_replacements("Import pie side six") == "Import PySide6"
        assert "kubectl" in manager.get_words()
        assert "PySide6" in manager.get_words()
