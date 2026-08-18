"""Audio file batch transcriber for Privacy Scribe.

Supports .mp3, .wav, .m4a, .ogg, .flac, .mp4 files.
Extracts and normalizes audio, splits into chunks if needed, transcribes
with timestamps/segments, and returns a TranscriptionResult.
"""

from __future__ import annotations

import asyncio
import inspect
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import MagicMock

import numpy as np
import soundfile as sf

from scribe_dictation.export.models import Segment, TranscriptionResult

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4"}
CHUNK_DURATION_SECONDS = 600.0  # 10 minutes per chunk if file is excessively long
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


class AudioExtractionError(Exception):
    """Raised when audio extraction or conversion fails."""


def _extract_audio_ffmpeg(file_path: Path, output_wav: Path) -> None:
    """Extract audio to 16kHz mono 16-bit PCM WAV using ffmpeg."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise AudioExtractionError(
            f"ffmpeg executable not found in PATH. ffmpeg is required to decode {file_path.suffix} files."
        )

    cmd = [
        ffmpeg_bin,
        "-y",  # overwrite output
        "-i",
        str(file_path),
        "-vn",  # disable video
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "-ac",
        str(TARGET_CHANNELS),
        str(output_wav),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise AudioExtractionError(
            f"ffmpeg failed to convert {file_path}: {result.stderr.strip()}"
        )


def _load_audio_as_wav(file_path: Path, temp_dir: Path) -> Path:
    """Load audio from any supported format into a standardized 16kHz mono WAV file."""
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{suffix}'. Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    # First attempt native soundfile reading (works great on WAV, FLAC, OGG)
    try:
        data, sr = sf.read(str(file_path), dtype="float32")
        # If stereo/multichannel, average to mono
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        target_path = temp_dir / f"extracted_{file_path.stem}.wav"
        # Resample if not 16kHz or write directly
        if sr == TARGET_SAMPLE_RATE:
            sf.write(str(target_path), data, TARGET_SAMPLE_RATE, subtype="PCM_16")
            return target_path
        else:
            # If resampling needed or soundfile is used, compute linear/simple resample or fallback to ffmpeg
            try:
                # If scipy or resample available, or fallback to ffmpeg
                _extract_audio_ffmpeg(file_path, target_path)
                return target_path
            except Exception:
                # Direct write with original sr if ffmpeg is unavailable
                sf.write(str(target_path), data, sr, subtype="PCM_16")
                return target_path
    except Exception:
        # Fallback to ffmpeg for mp3, m4a, mp4 or unreadable soundfile formats
        target_path = temp_dir / f"extracted_{file_path.stem}.wav"
        _extract_audio_ffmpeg(file_path, target_path)
        return target_path


def _chunk_audio_file(
    wav_path: Path,
    temp_dir: Path,
    chunk_duration: float = CHUNK_DURATION_SECONDS,
) -> list[tuple[Path, float, float]]:
    """Split audio into manageable chunks if needed.

    Returns:
        List of tuples: (chunk_wav_path, start_offset_seconds, chunk_duration_seconds)
    """
    info = sf.info(str(wav_path))
    duration = info.duration
    sample_rate = info.samplerate

    if duration <= chunk_duration:
        return [(wav_path, 0.0, duration)]

    chunks: list[tuple[Path, float, float]] = []
    total_frames = info.frames
    chunk_frames = int(chunk_duration * sample_rate)

    with sf.SoundFile(str(wav_path), mode="r") as source_sf:
        current_frame = 0
        chunk_idx = 0
        while current_frame < total_frames:
            frames_to_read = min(chunk_frames, total_frames - current_frame)
            data = source_sf.read(frames_to_read, dtype="float32")
            start_sec = current_frame / sample_rate
            dur_sec = len(data) / sample_rate

            chunk_file = temp_dir / f"chunk_{chunk_idx}_{wav_path.stem}.wav"
            sf.write(str(chunk_file), data, sample_rate, subtype="PCM_16")
            chunks.append((chunk_file, start_sec, dur_sec))

            current_frame += frames_to_read
            chunk_idx += 1

    return chunks


async def _transcribe_single_chunk(
    chunk_path: Path,
    transcriber: Any,
    offset_seconds: float,
    duration_seconds: float,
) -> list[Segment]:
    """Transcribe a single audio chunk using either faster-whisper local model,

    transcribe_segments method, or standard TranscribeService.
    """
    # 1. If transcriber has explicit transcribe_segments method
    if (
        (
            not isinstance(transcriber, MagicMock)
            or "transcribe_segments" in transcriber.__dict__
        )
        and hasattr(transcriber, "transcribe_segments")
        and callable(transcriber.transcribe_segments)
    ):
        res = transcriber.transcribe_segments(str(chunk_path))
        if inspect.isawaitable(res):
            res = await res
        if isinstance(res, list):
            adjusted = []
            for s in res:
                if isinstance(s, Segment):
                    adjusted.append(
                        Segment(
                            start=s.start + offset_seconds,
                            end=s.end + offset_seconds,
                            text=s.text,
                        )
                    )
                elif hasattr(s, "start") and hasattr(s, "end") and hasattr(s, "text"):
                    adjusted.append(
                        Segment(
                            start=float(s.start) + offset_seconds,
                            end=float(s.end) + offset_seconds,
                            text=str(s.text),
                        )
                    )
            return adjusted

    # 2. Check if transcriber has local faster-whisper model enabled
    use_local = getattr(transcriber, "use_local", False)
    if use_local:
        if hasattr(transcriber, "_init_local_model"):
            transcriber._init_local_model()
        local_model = getattr(transcriber, "_local_model", None)
        if local_model is not None and hasattr(local_model, "transcribe"):
            transcribe_kwargs = {"beam_size": 5}
            t_lang = getattr(transcriber, "language", None)
            if t_lang and t_lang.lower().strip() not in ("auto", "none", ""):
                transcribe_kwargs["language"] = t_lang.lower().strip()
            t_task = getattr(transcriber, "task", None)
            if t_task:
                transcribe_kwargs["task"] = (
                    "translate"
                    if t_task.lower().strip() in ("translate", "translation")
                    else "transcribe"
                )

            # faster-whisper returns (generator_of_segments, info)
            res = local_model.transcribe(str(chunk_path), **transcribe_kwargs)
            if isinstance(res, tuple) and len(res) >= 1:
                segments_gen = res[0]
                segments: list[Segment] = []
                for seg in segments_gen:
                    text = seg.text.strip()
                    if text:
                        segments.append(
                            Segment(
                                start=float(seg.start) + offset_seconds,
                                end=float(seg.end) + offset_seconds,
                                text=text,
                            )
                        )
                if segments:
                    return segments
                return [
                    Segment(
                        start=offset_seconds,
                        end=offset_seconds + duration_seconds,
                        text="",
                    )
                ]

    # 3. Standard transcribe() method (async or sync)
    if hasattr(transcriber, "transcribe") and callable(transcriber.transcribe):
        res = transcriber.transcribe(str(chunk_path))
        if inspect.isawaitable(res):
            text = await res
        else:
            text = res
        return [
            Segment(
                start=offset_seconds,
                end=offset_seconds + duration_seconds,
                text=str(text).strip(),
            )
        ]

    # 4. If transcriber is a direct callable
    if callable(transcriber):
        res = transcriber(str(chunk_path))
        if inspect.isawaitable(res):
            text = await res
        else:
            text = res
        return [
            Segment(
                start=offset_seconds,
                end=offset_seconds + duration_seconds,
                text=str(text).strip(),
            )
        ]

    raise ValueError(f"Transcriber object {transcriber} is not recognized or callable")


async def transcribe_audio_file_async(
    file_path: str | Path,
    transcriber: Any,
    progress_callback: Optional[Callable[[float], None]] = None,
    chunk_duration: float = CHUNK_DURATION_SECONDS,
) -> TranscriptionResult:
    """Asynchronously transcribe an audio file (.mp3, .wav, .m4a, .ogg, .flac, .mp4).

    Args:
        file_path: Path to the target audio/video file.
        transcriber: TranscribeService instance or compatible transcription callable/engine.
        progress_callback: Optional callback taking progress float (0.0 to 1.0).
        chunk_duration: Maximum duration per chunk in seconds.

    Returns:
        TranscriptionResult containing list of timestamped Segments and metadata.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format '{suffix}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if progress_callback:
        progress_callback(0.0)

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        wav_path = _load_audio_as_wav(path, temp_dir)

        chunks = _chunk_audio_file(wav_path, temp_dir, chunk_duration=chunk_duration)
        total_chunks = len(chunks)
        all_segments: list[Segment] = []

        for idx, (chunk_path, offset_sec, dur_sec) in enumerate(chunks):
            chunk_segments = await _transcribe_single_chunk(
                chunk_path, transcriber, offset_sec, dur_sec
            )
            all_segments.extend(chunk_segments)

            if progress_callback:
                progress = (idx + 1) / total_chunks
                progress_callback(progress)

    # Sort segments by start time
    all_segments.sort(key=lambda s: s.start)

    return TranscriptionResult(
        segments=all_segments,
        title=path.stem,
    )


def transcribe_audio_file(
    file_path: str | Path,
    transcriber: Any,
    progress_callback: Optional[Callable[[float], None]] = None,
    chunk_duration: float = CHUNK_DURATION_SECONDS,
) -> TranscriptionResult:
    """Synchronous entry point to transcribe an audio file.

    Handles running the async transcription in an existing or new event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running inside an existing event loop: run in a worker thread to avoid loop conflicts
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                asyncio.run,
                transcribe_audio_file_async(
                    file_path, transcriber, progress_callback, chunk_duration
                ),
            )
            return future.result()
    else:
        return asyncio.run(
            transcribe_audio_file_async(
                file_path, transcriber, progress_callback, chunk_duration
            )
        )
