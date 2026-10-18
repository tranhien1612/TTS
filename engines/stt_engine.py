import os
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Union, List
import numpy as np

from core.config import (
    WHISPER_DIR,
    WHISPER_DEFAULT_LANGUAGE,
)
from core.model_manager import ModelManager
from engines.base_engine import BaseAudioEngine

logger = logging.getLogger(__name__)


def format_srt(segments: List[Dict[str, Any]]) -> str:
    """Format speech segments into standard SubRip (.srt) subtitle format."""
    def format_timestamp(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        if millis >= 1000:
            secs += 1
            millis = 0
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    lines = []
    for idx, seg in enumerate(segments, start=1):
        start_ts = format_timestamp(seg.get("start", 0.0))
        end_ts = format_timestamp(seg.get("end", 0.0))
        text = seg.get("text", "").strip()
        lines.append(f"{idx}\n{start_ts} --> {end_ts}\n{text}\n")
    return "\n".join(lines)


def sync_text_to_segments(text: str, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Synchronize user-edited text back into timestamped segments while preserving timing."""
    if not text.strip():
        return []
    if not segments:
        return [{"start": 0.0, "end": 5.0, "text": text.strip()}]
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        raw_lines = [text.strip()]

    new_segments = [dict(s) for s in segments]
    if len(raw_lines) == len(new_segments):
        for i in range(len(new_segments)):
            new_segments[i]["text"] = raw_lines[i]
    elif len(raw_lines) < len(new_segments):
        for i in range(len(raw_lines)):
            new_segments[i]["text"] = raw_lines[i]
        for i in range(len(raw_lines), len(new_segments)):
            new_segments[i]["text"] = ""
    else:
        for i in range(len(new_segments) - 1):
            new_segments[i]["text"] = raw_lines[i]
        new_segments[-1]["text"] = " ".join(raw_lines[len(new_segments) - 1 :])

    return [s for s in new_segments if s.get("text", "").strip()]


class STTEngine(BaseAudioEngine):
    """Speech-to-Text engine using Whisper-Large-v3-Turbo with INT8 CPU quantization."""

    def __init__(self, model_dir: Path = WHISPER_DIR):
        super().__init__()
        self.model_dir = Path(model_dir)
        self.model_manager = ModelManager()
        self._engine = None
        self._lock = threading.Lock()

        # Hardware & Quantization setup: INT8 quantization on CPU
        try:
            import ctranslate2
            self.device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            self.device = "cpu"

        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self.cpu_threads = max(2, min(8, os.cpu_count() or 4))
        logger.info(f"STTEngine initialized with device={self.device}, compute_type={self.compute_type}")

    def is_model_downloaded(self) -> bool:
        """Check if local Whisper-Large-v3-Turbo weights exist in models/."""
        return self.model_manager.is_whisper_downloaded()

    def ensure_model_downloaded(self, progress_callback=None) -> bool:
        """Check and download Whisper-Large-v3-Turbo weights if missing."""
        return self.model_manager.ensure_whisper_model(progress_callback)

    def load_model(self, progress_callback=None) -> bool:
        """Load Whisper-Large-v3-Turbo model into memory with thread safety."""
        if self._is_loaded and self._engine is not None:
            return True

        with self._lock:
            if self._is_loaded and self._engine is not None:
                return True

            self.ensure_model_downloaded(progress_callback=progress_callback)

            if progress_callback:
                progress_callback(50, "Đang khởi tạo mô hình...")

            from faster_whisper import WhisperModel
            self._engine = WhisperModel(
                str(self.model_dir),
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
            )
            self._is_loaded = True
            logger.info("Whisper-Large-v3-Turbo model loaded successfully.")

            if progress_callback:
                progress_callback(100, "Mô hình Whisper đã sẵn sàng.")

            return True

    def unload_model(self) -> None:
        """Release Whisper model resources."""
        with self._lock:
            self._engine = None
            self._is_loaded = False
            import gc
            gc.collect()

    def transcribe(
        self,
        audio_source: Union[str, Path, np.ndarray],
        language: str = WHISPER_DEFAULT_LANGUAGE,
        beam_size: int = 1,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Transcribe speech to text from an audio file or raw numpy waveform."""
        self.load_model(progress_callback=progress_callback)
        if self._engine is None:
            raise RuntimeError("STT Engine chưa được khởi tạo.")

        if isinstance(audio_source, (str, Path)):
            audio_path = Path(audio_source).resolve()
            if not audio_path.exists():
                raise FileNotFoundError(f"Không tìm thấy tệp âm thanh: {audio_path}")
            audio_input = str(audio_path)
            source_name = audio_path.name
        else:
            audio_input = np.asarray(audio_source, dtype=np.float32)
            source_name = "Microphone"

        if progress_callback:
            progress_callback(0, "Đang nhận dạng âm thanh...")

        # Bắt đầu tính thời gian từ lúc chạy model thực tế (loại trừ thời gian tải và khởi tạo model)
        start_time = time.time()

        with self._lock:
            segments, info = self._engine.transcribe(
                audio_input,
                # language=language,
                beam_size=beam_size,
                vad_filter=True,
            )
            segments_data = []
            for s in segments:
                t = s.text.strip()
                if t:
                    segments_data.append({
                        "start": float(s.start),
                        "end": float(s.end),
                        "text": t,
                    })
            full_text = " ".join([seg["text"] for seg in segments_data])

        elapsed = time.time() - start_time
        import gc
        gc.collect()

        return {
            "text": full_text,
            "segments": segments_data,
            "language": getattr(info, "language", language),
            "language_probability": getattr(info, "language_probability", 1.0),
            "duration": getattr(info, "duration", 0.0),
            "elapsed_time": elapsed,
            "source": source_name,
        }

