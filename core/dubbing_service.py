"""Core dubbing service for video audio extraction, timeline-aligned TTS synthesis, and video muxing.

Provides end-to-end functionality for AI Video Dubbing:
1. Audio extraction from source video via FFmpeg.
2. Sentence-by-sentence TTS synthesis aligned with subtitle timestamps without overlap.
3. Audio-video remuxing removing old audio and attaching newly synthesized dubbed audio.
"""
import os
import shutil
import subprocess
import time
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

import numpy as np
import soundfile as sf

from core.config import OUTPUTS_DIR, get_ffmpeg_path, get_ffprobe_path, get_subprocess_no_window_kwargs
from engines.tts_engine import TTSEngine

logger = logging.getLogger(__name__)


def _run_subprocess(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """Run subprocess while completely suppressing console window on Windows."""
    no_win = get_subprocess_no_window_kwargs()
    merged = {**no_win, **kwargs}
    return subprocess.run(cmd, **merged)


def extract_audio_from_video(video_path: Path, output_audio_path: Optional[Path] = None) -> Path:
    """Extract audio from video file to 16kHz mono 16-bit PCM WAV (optimal for Whisper STT)."""
    if output_audio_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_audio_path = OUTPUTS_DIR / f"extracted_{timestamp}.wav"

    output_audio_path = Path(output_audio_path)
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        get_ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_audio_path),
    ]

    res = _run_subprocess(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg trích xuất âm thanh thất bại: {res.stderr}")

    if not output_audio_path.exists() or output_audio_path.stat().st_size == 0:
        raise RuntimeError("Không thể trích xuất âm thanh từ tệp video đã chọn.")

    return output_audio_path


def get_media_duration(file_path: Path) -> float:
    """Get accurate duration in seconds for video or audio file."""
    # First attempt: ffprobe
    try:
        cmd = [
            get_ffprobe_path(),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        res = _run_subprocess(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception as e:
        logger.debug(f"ffprobe failed for {file_path}: {e}")

    # Fallback for audio files: soundfile
    try:
        info = sf.info(str(file_path))
        return float(info.duration)
    except Exception:
        pass

    return 0.0


def get_video_resolution(file_path: Path) -> Optional[tuple[int, int]]:
    """Get video width and height in pixels using ffprobe."""
    try:
        cmd = [
            get_ffprobe_path(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(file_path),
        ]
        res = _run_subprocess(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split("x")
            if len(parts) == 2:
                w, h = int(parts[0]), int(parts[1])
                if w > 0 and h > 0:
                    return (w, h)
    except Exception as e:
        logger.debug(f"ffprobe resolution failed for {file_path}: {e}")
    return None


def adjust_audio_speed_atempo(audio_samples: np.ndarray, sr: int, speed: float) -> np.ndarray:
    """Adjust audio tempo without changing pitch using FFmpeg atempo filter."""
    if speed <= 1.02 and speed >= 0.98:
        return audio_samples

    with tempfile.TemporaryDirectory() as tmpdir:
        in_wav = Path(tmpdir) / "in.wav"
        out_wav = Path(tmpdir) / "out.wav"
        sf.write(str(in_wav), audio_samples, sr)

        # Build atempo filter chain if speed > 2.0 or < 0.5
        atempo_filters = []
        curr_speed = speed
        while curr_speed > 2.0:
            atempo_filters.append("atempo=2.0")
            curr_speed /= 2.0
        while curr_speed < 0.5:
            atempo_filters.append("atempo=0.5")
            curr_speed /= 0.5
        atempo_filters.append(f"atempo={curr_speed:.4f}")

        filter_str = ",".join(atempo_filters)
        cmd = [
            get_ffmpeg_path(),
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(in_wav),
            "-filter:a", filter_str,
            "-ar", str(sr),
            str(out_wav),
        ]
        res = _run_subprocess(cmd, capture_output=True, text=True)
        if res.returncode == 0 and out_wav.exists():
            sped_samples, _ = sf.read(str(out_wav), dtype="float32")
            if sped_samples.ndim > 1:
                sped_samples = sped_samples[:, 0]
            return sped_samples

    return audio_samples


def synthesize_timeline_audio(
    translated_segments: List[Dict[str, Any]],
    tts_engine: TTSEngine,
    total_duration: float,
    voice_ref: Optional[str] = None,
    base_speed: float = 1.0,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Path:
    """Synthesize voice for each translated segment and place it into a master timeline.

    Ensures that consecutive audio segments never overlap by dynamically adapting tempo
    and clamping to available timeslots.
    """
    valid_segs = [s for s in translated_segments if s.get("text", "").strip()]
    if not valid_segs:
        raise ValueError("Không có nội dung câu thoại nào để tạo giọng nói.")

    sr = getattr(tts_engine, "sample_rate", 24000) or 24000

    # Ensure total_duration is at least as long as the last segment
    last_end = max((float(s.get("end", 0.0)) for s in valid_segs), default=0.0)
    effective_duration = max(total_duration, last_end + 1.0)
    master_len = int(np.ceil((effective_duration + 2.0) * sr))
    master_buffer = np.zeros(master_len, dtype=np.float32)

    total_count = len(valid_segs)
    for i, seg in enumerate(valid_segs):
        text = seg.get("text", "").strip()
        start_sec = max(0.0, float(seg.get("start", 0.0)))
        end_sec = max(start_sec, float(seg.get("end", start_sec + 1.0)))

        # Determine upper boundary: next segment's start time or total duration
        if i + 1 < total_count:
            next_start_sec = max(start_sec + 0.3, float(valid_segs[i + 1].get("start", end_sec)))
        else:
            next_start_sec = effective_duration

        max_available_dur = max(0.3, next_start_sec - start_sec)

        pct = int((i / total_count) * 100)
        if progress_callback:
            progress_callback(pct, f"Đang tạo giọng nói câu {i + 1}/{total_count}...")

        # Synthesize audio segment via TTS engine
        res = tts_engine.synthesize(text, voice_ref=voice_ref, speed=base_speed)
        raw_audio: np.ndarray = res["audio"]
        chunk_sr: int = res["sample_rate"]

        # Ensure 1D float32
        if raw_audio.ndim > 1:
            raw_audio = raw_audio[:, 0]
        if raw_audio.dtype != np.float32:
            raw_audio = raw_audio.astype(np.float32)

        # Resample if chunk_sr != sr
        if chunk_sr != sr and chunk_sr > 0:
            target_len = int(len(raw_audio) * (sr / chunk_sr))
            raw_audio = np.interp(
                np.linspace(0, len(raw_audio), target_len, endpoint=False),
                np.arange(len(raw_audio)),
                raw_audio,
            ).astype(np.float32)

        chunk_dur = len(raw_audio) / sr

        # If audio chunk exceeds the timeslot before next sentence, speed it up so it won't overlap!
        if chunk_dur > max_available_dur:
            speed_ratio = chunk_dur / (max_available_dur * 0.95)
            # Cap maximum acceleration to 2.5x to preserve speech clarity
            speed_ratio = min(2.5, speed_ratio)
            raw_audio = adjust_audio_speed_atempo(raw_audio, sr, speed_ratio)

        # Place into master timeline strictly within bounds
        start_idx = int(start_sec * sr)
        max_end_idx = int(next_start_sec * sr)
        end_idx = min(start_idx + len(raw_audio), master_len, max_end_idx)

        chunk_to_insert = raw_audio[: end_idx - start_idx]

        # Apply gentle 5ms fade-out at the end to prevent audio clicks
        fade_len = min(int(0.005 * sr), len(chunk_to_insert))
        if fade_len > 0:
            fade_curve = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
            chunk_to_insert[-fade_len:] *= fade_curve

        master_buffer[start_idx : start_idx + len(chunk_to_insert)] = chunk_to_insert

    if progress_callback:
        progress_callback(100, "Hoàn tất ghép nối dòng thời gian âm thanh!")

    # Crop to final duration
    final_length = int(np.ceil(effective_duration * sr))
    final_audio = master_buffer[:final_length]

    # Save output
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_wav_path = OUTPUTS_DIR / f"dubbed_audio_{timestamp}.wav"
    sf.write(str(out_wav_path), final_audio, sr)

    return out_wav_path


def merge_audio_into_video(
    video_path: Path,
    dubbed_audio_path: Path,
    output_video_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Path:
    """Remux video with newly synthesized dubbed audio, completely replacing old audio.

    Uses stream copy for video stream (-c:v copy) to guarantee zero quality loss and near-instant muxing.
    Encodes audio to high quality AAC for universal playback compatibility.
    """
    if output_video_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        stem = Path(video_path).stem
        output_video_path = OUTPUTS_DIR / f"{stem}_dubbed_{timestamp}.mp4"

    output_video_path = Path(output_video_path)
    output_video_path.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(30, "Đang ghép âm thanh thuyết minh vào video...")

    cmd = [
        get_ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-i", str(dubbed_audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_video_path),
    ]

    res = _run_subprocess(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg ghép video thất bại: {res.stderr}")

    if not output_video_path.exists() or output_video_path.stat().st_size == 0:
        raise RuntimeError("Không thể tạo tệp video đầu ra.")

    if progress_callback:
        progress_callback(100, "✓ Đã tạo video thuyết minh thành công!")

    return output_video_path


def burn_subtitles_into_video(
    video_path: Path,
    srt_path: Path,
    output_video_path: Optional[Path] = None,
    font_size: int = 18,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Path:
    """Burn subtitles directly into the video stream (hardsub), preserving the original audio.

    Renders styled subtitles at the bottom center of the video using FFmpeg's subtitles filter.
    """
    if output_video_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        stem = Path(video_path).stem
        output_video_path = OUTPUTS_DIR / f"{stem}_subtitled_{timestamp}.mp4"

    output_video_path = Path(output_video_path)
    output_video_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path = Path(srt_path).resolve()

    if progress_callback:
        progress_callback(25, "Đang gán phụ đề vào video...")

    # Using filename with cwd=srt_path.parent to avoid all Windows path colon / backslash escaping issues
    vf_filter = (
        f"subtitles=filename='{srt_path.name}':"
        f"force_style='FontSize={font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=25'"
    )

    cmd = [
        get_ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-vf", vf_filter,
        "-c:a", "copy",
        str(output_video_path),
    ]

    res = _run_subprocess(cmd, cwd=str(srt_path.parent), capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg gán phụ đề thất bại: {res.stderr}")

    if not output_video_path.exists() or output_video_path.stat().st_size == 0:
        raise RuntimeError("Không thể tạo tệp video có phụ đề.")

    if progress_callback:
        progress_callback(100, "✓ Đã gán phụ đề vào video thành công!")

    return output_video_path

