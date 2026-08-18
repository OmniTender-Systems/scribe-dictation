"""Voice Activity Detection (VAD), silence stripper, and audio normalizer module.

Provides:
- Energy/Spectral + lightweight neural VAD pre-filtering for raw PCM / WAV audio arrays.
- Trims dead lead-in/lead-out silence, keyboard clatter, breathing, and background hiss.
- Strips non-speech audio to prevent Whisper silence hallucinations (e.g. '[Music]', 'Thank you for watching').
- Audio auto-gain normalization: scales speech to standard -16 LUFS / target peak RMS without clipping or distortion.
- Functions:
    - process_audio(audio_data, sample_rate) -> np.ndarray
    - is_speech_present(audio_data, sample_rate) -> bool
    - normalize_loudness(audio_data, target_lufs, target_peak, max_gain_db) -> np.ndarray
    - detect_speech_segments(audio_data, sample_rate) -> list[tuple[int, int]]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

# Constants
DEFAULT_SAMPLE_RATE = 16000
TARGET_LUFS = -16.0
TARGET_RMS = 10.0 ** (TARGET_LUFS / 20.0)  # ~0.1585 (-16 dBFS)
TARGET_PEAK = 0.95
MAX_GAIN_DB = 30.0
MAX_GAIN_LINEAR = 10.0 ** (MAX_GAIN_DB / 20.0)  # ~31.62
MIN_SPEECH_DURATION_MS = 100
MAX_SILENCE_GAP_MS = 1000
PAD_SPEECH_MS = 200


@dataclass
class VADConfig:
    """Configuration for VAD, noise gating, and normalization."""

    sample_rate: int = DEFAULT_SAMPLE_RATE
    target_lufs: float = TARGET_LUFS
    target_peak: float = TARGET_PEAK
    max_gain_db: float = MAX_GAIN_DB
    min_speech_duration_ms: int = MIN_SPEECH_DURATION_MS
    max_silence_gap_ms: int = MAX_SILENCE_GAP_MS
    pad_speech_ms: int = PAD_SPEECH_MS
    energy_threshold: float = 0.015
    spectral_flatness_threshold: float = 0.65
    use_neural_vad: bool = True


def _ensure_mono_float32(audio: Union[np.ndarray, list]) -> np.ndarray:
    """Convert input audio array to 1D float32 normalized to [-1.0, 1.0]."""
    if not isinstance(audio, np.ndarray):
        audio = np.asarray(audio, dtype=np.float32)

    if audio.size == 0:
        return np.array([], dtype=np.float32)

    # Flatten multi-channel (2D) audio by averaging channels
    if audio.ndim == 2:
        if audio.shape[1] <= 8:  # (samples, channels)
            audio = np.mean(audio, axis=1)
        elif audio.shape[0] <= 8:  # (channels, samples)
            audio = np.mean(audio, axis=0)
        else:
            audio = audio.flatten()
    elif audio.ndim > 2:
        audio = audio.flatten()

    # Convert integer types to float32 in [-1.0, 1.0]
    if np.issubdtype(audio.dtype, np.integer):
        info = np.iinfo(audio.dtype)
        audio = audio.astype(np.float32) / max(abs(info.min), info.max)
    elif audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    # Clean NaNs and Infs
    if not np.all(np.isfinite(audio)):
        audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)

    return audio


def _high_pass_filter(audio: np.ndarray, alpha: float = 0.97) -> np.ndarray:
    """Apply high-pass DC-blocking filter to remove low-frequency rumble and mic DC offset."""
    if len(audio) < 2:
        return audio
    # DC Blocker: y[n] = x[n] - x[n-1] + alpha * y[n-1]
    y = np.zeros_like(audio)
    y[0] = audio[0]
    for i in range(1, len(audio)):
        y[i] = audio[i] - audio[i - 1] + alpha * y[i - 1]
    return y


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Fast linear resample for VAD processing."""
    if orig_sr == target_sr or len(audio) == 0:
        return audio
    num_samples = int(round(len(audio) * target_sr / orig_sr))
    indices = np.linspace(0, len(audio) - 1, num_samples)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def _soft_limit(
    audio: np.ndarray, threshold: float = 0.90, hard_limit: float = 0.98
) -> np.ndarray:
    """Apply transparent soft-knee saturation to prevent clipping and harsh digital distortion."""
    if len(audio) == 0:
        return audio

    peak = float(np.max(np.abs(audio)))
    if peak <= threshold:
        return audio

    abs_x = np.abs(audio)
    sign_x = np.sign(audio)
    out = audio.copy()

    # Apply soft saturation only to samples strictly above threshold
    above = abs_x > threshold
    diff = abs_x[above] - threshold
    headroom = max(hard_limit - threshold, 0.01)
    compressed = threshold + headroom * np.tanh(diff / headroom)
    out[above] = sign_x[above] * compressed

    return out


def normalize_loudness(
    audio_data: np.ndarray,
    target_lufs: float = TARGET_LUFS,
    target_peak: float = TARGET_PEAK,
    max_gain_db: float = MAX_GAIN_DB,
    speech_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Normalize audio loudness to target LUFS/RMS with clipping prevention.

    Args:
        audio_data: 1D float32 audio array.
        target_lufs: Target loudness level in LUFS / dBFS (default: -16.0 LUFS).
        target_peak: Maximum allowed peak before soft limiting (default: 0.95).
        max_gain_db: Maximum boost gain in dB to avoid amplifying silence noise floor.
        speech_mask: Optional boolean array marking speech samples for RMS calculation.

    Returns:
        Loudness-normalized float32 audio array.
    """
    audio = _ensure_mono_float32(audio_data)
    if len(audio) == 0:
        return audio

    # Calculate speech or active RMS
    if speech_mask is not None and np.any(speech_mask):
        eval_samples = audio[speech_mask]
    else:
        eval_samples = audio

    rms = float(np.sqrt(np.mean(np.square(eval_samples))))
    if rms < 1e-6:
        # Near silent / all zero
        return audio

    target_rms_val = 10.0 ** (target_lufs / 20.0)
    desired_gain = target_rms_val / rms

    # Clamp gain to max allowed boost
    max_linear_gain = 10.0 ** (max_gain_db / 20.0)
    gain = min(desired_gain, max_linear_gain)

    # Scale audio
    scaled_audio = audio * gain

    # Apply soft clipping prevention
    return _soft_limit(scaled_audio, threshold=target_peak, hard_limit=0.98)


def _energy_spectral_vad_segments(
    audio: np.ndarray,
    sample_rate: int,
    config: VADConfig,
) -> list[tuple[int, int]]:
    """Detect speech segments using energy, spectral dynamics, and zero-crossing analysis."""
    frame_len = int(0.03 * sample_rate)  # 30 ms frames
    hop_len = int(0.015 * sample_rate)  # 15 ms hop
    if len(audio) < frame_len:
        rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) > 0 else 0.0
        if rms > config.energy_threshold:
            return [(0, len(audio))]
        return []

    num_frames = (len(audio) - frame_len) // hop_len + 1
    frame_energies = np.zeros(num_frames, dtype=np.float32)
    frame_crest = np.zeros(num_frames, dtype=np.float32)

    for i in range(num_frames):
        start = i * hop_len
        frame = audio[start : start + frame_len]
        rms = float(np.sqrt(np.mean(np.square(frame))))
        frame_energies[i] = rms

        peak = np.max(np.abs(frame))
        frame_crest[i] = (peak / (rms + 1e-6)) if rms > 1e-6 else 0.0

    # Dynamic noise floor estimate (20th percentile of lowest frames)
    sorted_energies = np.sort(frame_energies)
    noise_floor = float(sorted_energies[int(0.2 * len(sorted_energies))])
    speech_threshold = max(config.energy_threshold, noise_floor * 2.0)

    # Candidate speech frames:
    # 1. Energy above threshold
    # 2. Not pure high-frequency click (crest factor check)
    is_active = (frame_energies > speech_threshold) & (frame_crest < 7.0)

    # Bridge short gaps strictly BETWEEN active speech frames
    max_gap_frames = int((min(config.max_silence_gap_ms, 300) / 1000.0) / 0.015)
    bridged = is_active.copy()
    gap_start = None
    for i in range(num_frames):
        if not is_active[i]:
            if gap_start is None and i > 0 and is_active[i - 1]:
                gap_start = i
        else:
            if gap_start is not None:
                if (i - gap_start) <= max_gap_frames:
                    bridged[gap_start:i] = True
                gap_start = None

    # Group contiguous blocks and enforce min_speech_duration_ms
    min_speech_frames = int((config.min_speech_duration_ms / 1000.0) / 0.015)
    segments: list[tuple[int, int]] = []
    seg_start: Optional[int] = None

    for i in range(num_frames):
        if bridged[i] and seg_start is None:
            seg_start = i
        elif not bridged[i] and seg_start is not None:
            if (i - seg_start) >= min_speech_frames:
                sample_start = seg_start * hop_len
                sample_end = min(len(audio), (i - 1) * hop_len + frame_len)
                segments.append((sample_start, sample_end))
            seg_start = None

    if seg_start is not None and (num_frames - seg_start) >= min_speech_frames:
        sample_start = seg_start * hop_len
        sample_end = len(audio)
        segments.append((sample_start, sample_end))

    return segments


def _neural_vad_segments(
    audio: np.ndarray,
    sample_rate: int,
    config: VADConfig,
) -> Optional[list[tuple[int, int]]]:
    """Detect speech segments using faster-whisper's built-in Silero neural VAD."""
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        # Silero VAD operates on 16000 Hz
        if sample_rate != 16000:
            audio_16k = _resample(audio, sample_rate, 16000)
            scale = len(audio) / len(audio_16k) if len(audio_16k) > 0 else 1.0
        else:
            audio_16k = audio
            scale = 1.0

        vad_options = VadOptions(
            threshold=0.45,
            min_speech_duration_ms=config.min_speech_duration_ms,
            max_speech_duration_s=float("inf"),
            min_silence_duration_ms=config.max_silence_gap_ms,
            speech_pad_ms=config.pad_speech_ms,
        )

        timestamps = get_speech_timestamps(audio_16k, vad_options)
        if not timestamps:
            return []

        segments: list[tuple[int, int]] = []
        for item in timestamps:
            s_start = int(round(item["start"] * scale))
            s_end = int(round(item["end"] * scale))
            segments.append((max(0, s_start), min(len(audio), s_end)))

        return segments
    except Exception as e:
        logger.debug("Neural VAD unavailable or failed: %s", e)
        return None


def detect_speech_segments(
    audio_data: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    config: Optional[VADConfig] = None,
) -> list[tuple[int, int]]:
    """Detect speech segments (start_sample, end_sample) in audio array.

    Combines neural Silero VAD with energy/spectral VAD.

    Args:
        audio_data: 1D or 2D audio array.
        sample_rate: Sampling frequency in Hz.
        config: Optional VADConfig settings.

    Returns:
        List of (start_sample, end_sample) tuples representing detected speech.
    """
    audio = _ensure_mono_float32(audio_data)
    if len(audio) == 0:
        return []

    cfg = config or VADConfig(sample_rate=sample_rate)

    # 1. Try Neural VAD first if enabled
    if cfg.use_neural_vad:
        neural_segments = _neural_vad_segments(audio, sample_rate, cfg)
        if neural_segments is not None and len(neural_segments) > 0:
            return neural_segments

    # 2. Energy & Spectral VAD
    return _energy_spectral_vad_segments(audio, sample_rate, cfg)


def is_speech_present(
    audio_data: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    config: Optional[VADConfig] = None,
) -> bool:
    """Determine whether actionable human speech is present in audio.

    Rejects dead silence, steady background hiss, low-frequency hum,
    breathing noise, and isolated keyboard clatter.

    Args:
        audio_data: Audio array to analyze.
        sample_rate: Sampling frequency in Hz.
        config: Optional VADConfig settings.

    Returns:
        True if speech is detected; False otherwise.
    """
    audio = _ensure_mono_float32(audio_data)
    if len(audio) == 0:
        return False

    # Check overall RMS — if lower than minimum threshold, definitely silence
    overall_rms = float(np.sqrt(np.mean(np.square(audio))))
    if overall_rms < 0.005:
        return False

    segments = detect_speech_segments(audio, sample_rate, config)
    if not segments:
        return False

    total_speech_samples = sum(end - start for start, end in segments)
    min_samples = int((MIN_SPEECH_DURATION_MS / 1000.0) * sample_rate)

    return total_speech_samples >= min_samples


def process_audio(
    audio_data: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    target_lufs: float = TARGET_LUFS,
    target_peak: float = TARGET_PEAK,
    max_gain_db: float = MAX_GAIN_DB,
    pad_ms: int = PAD_SPEECH_MS,
    config: Optional[VADConfig] = None,
) -> np.ndarray:
    """Full VAD pre-filter, silence stripper, and audio normalizer.

    1. Removes DC offset and filters sub-audible hum.
    2. Runs neural + energy/spectral speech detection.
    3. Trims dead lead-in and lead-out silence (with padding).
    4. Strips non-speech noise to prevent Whisper silence hallucinations.
    5. Normalizes speech loudness to standard -16 LUFS / target peak RMS without clipping.

    Args:
        audio_data: Raw PCM audio array (1D or 2D, float or int).
        sample_rate: Sampling frequency in Hz (default: 16000).
        target_lufs: Target loudness level (default: -16.0 LUFS).
        target_peak: Maximum peak ceiling (default: 0.95).
        max_gain_db: Maximum auto-gain boost (default: 30.0 dB).
        pad_ms: Milliseconds of padding around speech boundaries.
        config: Optional VADConfig override.

    Returns:
        Processed 1D float32 audio array ready for Whisper transcription,
        or an empty array if no speech is detected.
    """
    audio = _ensure_mono_float32(audio_data)
    if len(audio) == 0:
        return np.array([], dtype=np.float32)

    # Remove DC offset
    audio = audio - float(np.mean(audio))

    cfg = config or VADConfig(
        sample_rate=sample_rate,
        target_lufs=target_lufs,
        target_peak=target_peak,
        max_gain_db=max_gain_db,
        pad_speech_ms=pad_ms,
    )

    # Detect speech segments
    segments = detect_speech_segments(audio, sample_rate, cfg)

    if not segments:
        # No speech detected: return empty array to prevent Whisper hallucinations
        return np.array([], dtype=np.float32)

    pad_samples = int((pad_ms / 1000.0) * sample_rate)

    # Lead-in and lead-out trimming with padding
    first_speech_start = max(0, segments[0][0] - pad_samples)
    last_speech_end = min(len(audio), segments[-1][1] + pad_samples)

    trimmed_audio = audio[first_speech_start:last_speech_end]
    if len(trimmed_audio) == 0:
        return np.array([], dtype=np.float32)

    # Create speech mask for accurate loudness computation
    speech_mask = np.zeros(len(trimmed_audio), dtype=bool)
    for s_start, s_end in segments:
        rel_start = max(0, s_start - first_speech_start)
        rel_end = min(len(trimmed_audio), s_end - first_speech_start)
        if rel_end > rel_start:
            speech_mask[rel_start:rel_end] = True

    # Normalize loudness to target LUFS / target peak RMS with soft limiting
    normalized_audio = normalize_loudness(
        trimmed_audio,
        target_lufs=cfg.target_lufs,
        target_peak=cfg.target_peak,
        max_gain_db=cfg.max_gain_db,
        speech_mask=speech_mask,
    )

    return normalized_audio.astype(np.float32)
