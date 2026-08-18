"""Voice Lab & Accuracy Calibration Engine for Privacy Scribe.

Provides:
- Phonetically balanced calibration sentences targeting diverse phonemes, tech terms, vowels, and numbers.
- CalibrationResult: Dataclass capturing speech metrics (WPM, amplitude, SNR, optimal thresholds).
- VoiceCalibrationRunner: Analyzes recorded audio signals and computes voice metrics.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np

try:
    import soundfile as sf
except ImportError:
    sf = None  # type: ignore


# ---------------------------------------------------------------------------
# Calibration Sentences
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationSentence:
    """Represents a calibration sentence targeting specific phonetic or lexical characteristics."""

    id: str
    text: str
    target_category: str
    target_phonemes: str
    word_count: int

    @classmethod
    def create(
        cls, id: str, text: str, category: str, phonemes: str
    ) -> CalibrationSentence:
        words = [w for w in text.split() if w.strip()]
        return cls(
            id=id,
            text=text,
            target_category=category,
            target_phonemes=phonemes,
            word_count=len(words),
        )


CALIBRATION_SENTENCES: tuple[CalibrationSentence, ...] = (
    CalibrationSentence.create(
        id="general_phonetic",
        text="The quick brown fox jumps over the lazy dog near the vibrant river bank.",
        category="General Phonetics",
        phonemes="Pangram, diverse English vowels & plosives /b/, /p/, /d/, /g/, /k/",
    ),
    CalibrationSentence.create(
        id="vowels_diphthongs",
        text="Audio engineering requires unique acoustic awareness and extraordinary patience.",
        category="Vowels & Diphthongs",
        phonemes="/ɔː/, /ɪə/, /aɪ/, /eɪ/, /uː/, long & short vowels",
    ),
    CalibrationSentence.create(
        id="sibilants_fricatives",
        text="Six fresh fish swiftly swam through sixty-six shallow surging streams.",
        category="Sibilants & Fricatives",
        phonemes="/s/, /ʃ/, /f/, /θ/, high-frequency gating",
    ),
    CalibrationSentence.create(
        id="tech_jargon",
        text="Deploying Kubernetes microservices with PostgreSQL, Redis cache, and GraphQL APIs.",
        category="Tech & Developer Jargon",
        phonemes="Technical abbreviations, acronyms, compound code terms",
    ),
    CalibrationSentence.create(
        id="numbers_dates",
        text="On July 24th, 2026, version 3.14 was delivered at 8:45 AM across 1,250 servers.",
        category="Numbers & Timestamps",
        phonemes="Ordinal & cardinal numbers, decimals, timestamps, quantities",
    ),
    CalibrationSentence.create(
        id="conversational_flow",
        text="Privacy Scribe processes dictation locally without sending unencrypted voice data to cloud servers.",
        category="Conversational Flow",
        phonemes="Natural sentence pacing, polysyllabic words, privacy terminology",
    ),
)


# ---------------------------------------------------------------------------
# Calibration Metrics Dataclass
# ---------------------------------------------------------------------------


@dataclass
class CalibrationResult:
    """Quantitative speech and audio metrics calculated from calibration recording."""

    duration_seconds: float
    spoken_word_count: int
    wpm: float  # Words Per Minute
    average_rms: float  # Average vocal root mean square amplitude (0.0 to 1.0)
    peak_amplitude: float  # Peak absolute amplitude (0.0 to 1.0)
    noise_floor_rms: float  # Background noise floor RMS amplitude
    snr_db: float  # Signal-to-noise ratio in decibels
    recommended_silence_threshold: float  # Optimal RMS threshold for silence gating
    recommended_silence_duration: float  # Optimal silence timeout in seconds
    recommended_gain_factor: float  # Suggested input gain multiplier (e.g. 1.0 to 2.5)
    quality_grade: str  # "Excellent", "Good", "Fair", "Poor"
    feedback_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationResult:
        return cls(**data)


# ---------------------------------------------------------------------------
# Calibration Runner
# ---------------------------------------------------------------------------


class VoiceCalibrationRunner:
    """Calculates speech cadence, audio amplitude, SNR, and gating thresholds."""

    def __init__(self, default_sample_rate: int = 16000) -> None:
        self.default_sample_rate = default_sample_rate

    @staticmethod
    def get_sentences() -> list[CalibrationSentence]:
        """Return list of predefined calibration sentences."""
        return list(CALIBRATION_SENTENCES)

    def analyze_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        expected_word_count: Optional[int] = None,
        frame_duration_ms: float = 20.0,
    ) -> CalibrationResult:
        """Analyze raw audio numpy array and compute calibration metrics.

        Args:
            audio_data: Audio array (1D float32 or int16, or 2D multichannel).
            sample_rate: Audio sampling frequency in Hz.
            expected_word_count: Optional count of words read from prompt sentence.
            frame_duration_ms: Frame window for short-time energy calculation.

        Returns:
            CalibrationResult with calculated metrics.
        """
        # Convert to 1D float32 normalized [-1.0, 1.0]
        samples = self._normalize_audio(audio_data)

        if len(samples) == 0:
            return CalibrationResult(
                duration_seconds=0.0,
                spoken_word_count=0,
                wpm=0.0,
                average_rms=0.0,
                peak_amplitude=0.0,
                noise_floor_rms=0.0,
                snr_db=0.0,
                recommended_silence_threshold=0.01,
                recommended_silence_duration=1.5,
                recommended_gain_factor=1.0,
                quality_grade="Poor",
                feedback_notes=["No audio signal detected."],
            )

        duration = float(len(samples)) / float(sample_rate)

        # Peak absolute amplitude
        peak_amplitude = float(np.max(np.abs(samples)))

        # Frame-by-frame RMS energy analysis
        frame_len = max(1, int(sample_rate * (frame_duration_ms / 1000.0)))
        num_frames = len(samples) // frame_len

        if num_frames == 0:
            frame_rms = np.array([float(np.sqrt(np.mean(samples**2)))])
        else:
            frames = samples[: num_frames * frame_len].reshape((num_frames, frame_len))
            frame_rms = np.sqrt(np.mean(frames**2, axis=1))

        # Estimate noise floor vs speech energy
        sorted_rms = np.sort(frame_rms)
        noise_idx = max(1, int(len(sorted_rms) * 0.15))
        noise_floor_rms = float(np.mean(sorted_rms[:noise_idx]))

        # High energy frames (top 60%)
        top_idx = int(len(sorted_rms) * 0.40)
        speech_frames = sorted_rms[top_idx:]

        if len(speech_frames) > 0:
            average_rms = float(np.mean(speech_frames))
        else:
            average_rms = float(np.mean(frame_rms))

        # Calculate SNR (Signal-to-Noise Ratio) in dB
        # Ensure a minimum practical floor to prevent divide-by-zero or artifact 0dB
        effective_noise_floor = max(noise_floor_rms, 1e-4)
        if average_rms > effective_noise_floor:
            snr_db = float(20.0 * math.log10(average_rms / effective_noise_floor))
        else:
            snr_db = 0.0

        # WPM estimation
        words = (
            expected_word_count
            if (expected_word_count and expected_word_count > 0)
            else self._estimate_word_count(
                frame_rms, noise_floor_rms, sample_rate, frame_len
            )
        )
        if duration > 0.5:
            wpm = float((words / duration) * 60.0)
        else:
            wpm = 0.0

        # Compute recommended silence gating threshold and duration
        recommended_threshold = float(
            np.clip(noise_floor_rms * 1.8 + 0.002, 0.005, 0.08)
        )

        # Recommended silence duration: faster talkers (higher WPM) get tighter silence timeout (1.0 - 1.2s),
        # slower speakers get more breathing room (1.5 - 2.0s)
        if wpm > 150:
            rec_silence_duration = 1.2
        elif wpm > 110:
            rec_silence_duration = 1.5
        elif wpm > 0:
            rec_silence_duration = 1.8
        else:
            rec_silence_duration = 1.5

        # Gain factor recommendation (aiming for peak around 0.70 - 0.85 without clipping)
        if peak_amplitude > 0.01:
            rec_gain = float(np.clip(0.75 / peak_amplitude, 0.5, 3.5))
        else:
            rec_gain = 1.0

        # Quality grade & diagnostic feedback
        feedback_notes = []
        if snr_db >= 22.0 and peak_amplitude >= 0.20:
            quality_grade = "Excellent"
            feedback_notes.append("Crystal clear audio with low background noise.")
        elif snr_db >= 14.0 and peak_amplitude >= 0.10:
            quality_grade = "Good"
            feedback_notes.append(
                "Good voice clarity suitable for high-accuracy local transcription."
            )
        elif snr_db >= 7.0 or peak_amplitude >= 0.05:
            quality_grade = "Fair"
            feedback_notes.append(
                "Moderate background noise or low microphone input level."
            )
        else:
            quality_grade = "Poor"
            feedback_notes.append(
                "High background noise or very low microphone volume."
            )

        if peak_amplitude > 0.95:
            feedback_notes.append(
                "Microphone clipping detected. Consider lowering microphone gain or moving back."
            )
        elif peak_amplitude < 0.15:
            feedback_notes.append(
                "Microphone signal is quiet. Consider speaking closer or boosting input gain."
            )

        if snr_db < 10.0 and duration > 1.0:
            feedback_notes.append(
                "Substantial background noise detected. An acoustic gate or quiet room is recommended."
            )

        if wpm > 185:
            feedback_notes.append(
                "Fast speech cadence detected. Scribe will adapt silence gating accordingly."
            )
        elif 0 < wpm < 85:
            feedback_notes.append(
                "Measured slow speech cadence. Extended silence threshold applied."
            )

        return CalibrationResult(
            duration_seconds=round(duration, 2),
            spoken_word_count=words,
            wpm=round(wpm, 1),
            average_rms=round(average_rms, 4),
            peak_amplitude=round(peak_amplitude, 4),
            noise_floor_rms=round(noise_floor_rms, 4),
            snr_db=round(snr_db, 1),
            recommended_silence_threshold=round(recommended_threshold, 4),
            recommended_silence_duration=round(rec_silence_duration, 2),
            recommended_gain_factor=round(rec_gain, 2),
            quality_grade=quality_grade,
            feedback_notes=feedback_notes,
        )

    def analyze_file(
        self,
        audio_file_path: str,
        expected_word_count: Optional[int] = None,
    ) -> CalibrationResult:
        """Load audio file and compute calibration metrics."""
        if sf is None:
            raise RuntimeError("soundfile library is required to read audio files.")

        data, sample_rate = sf.read(audio_file_path, dtype="float32")
        return self.analyze_audio(
            audio_data=data,
            sample_rate=sample_rate,
            expected_word_count=expected_word_count,
        )

    def _normalize_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """Convert input array to 1D float32 normalized between -1.0 and 1.0."""
        if audio_data is None or audio_data.size == 0:
            return np.array([], dtype=np.float32)

        arr = np.asarray(audio_data)

        # Multi-channel to mono (average channels)
        if arr.ndim > 1:
            arr = np.mean(arr, axis=1)

        # Convert integer types to float32 normalized
        if np.issubdtype(arr.dtype, np.integer):
            info = np.iinfo(arr.dtype)
            arr = arr.astype(np.float32) / max(abs(info.min), info.max)
        else:
            arr = arr.astype(np.float32)

        return arr

    def _estimate_word_count(
        self,
        frame_rms: np.ndarray,
        noise_floor: float,
        sample_rate: int,
        frame_len: int,
    ) -> int:
        """Estimate spoken syllable/word groups using energy peaks when expected count is not given."""
        if len(frame_rms) == 0:
            return 0

        threshold = max(noise_floor * 2.5, 0.015)
        is_speech = frame_rms > threshold

        # Count state transitions from non-speech to speech with minimum duration
        bursts = 0
        in_burst = False
        burst_len = 0
        min_frames = int(0.12 / (frame_len / sample_rate))  # at least ~120ms burst

        for active in is_speech:
            if active:
                burst_len += 1
                if not in_burst and burst_len >= min_frames:
                    bursts += 1
                    in_burst = True
            else:
                burst_len = 0
                in_burst = False

        return max(1, bursts)
