import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np
import soundfile as sf

from core.config import (
    DEFAULT_MODEL_MODE,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_VOICE,
    OUTPUTS_DIR,
    MODEL_VIENEU,
    MODEL_OMNIVOICE,
    DEFAULT_TTS_MODEL,
    OMNIVOICE_REPO,
    OMNIVOICE_SAMPLE_RATE,
)
from core.model_manager import ModelManager
from engines.base_engine import BaseAudioEngine

logger = logging.getLogger(__name__)


# OmniVoice has no default voices; it supports zero-shot voice cloning only
OMNIVOICE_PRESETS: List[Dict[str, Any]] = []


class TTSEngine(BaseAudioEngine):
    """Multi-model TTS engine supporting VieNeu, OmniVoice, and Kokoro."""

    def __init__(self, mode: str = DEFAULT_MODEL_MODE):
        super().__init__()
        self.mode = mode
        self.model_manager = ModelManager()
        self._engine: Optional[Any] = None
        self._lock = threading.Lock()
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.current_model_type: str = DEFAULT_TTS_MODEL
        self._preset_voices: List[Dict[str, str]] = []
        self._load_cached_preset_voices()

    # ─── Model type switching ───────────────────────────────────────────

    def set_model_type(self, model_type: str) -> None:
        """Switch to a different TTS model. Unloads the current model if loaded."""
        if model_type == self.current_model_type and self._is_loaded:
            return
        self.unload_model()
        self.current_model_type = model_type
        self._load_cached_preset_voices()

    @property
    def supports_voice_clone(self) -> bool:
        """Whether the current model supports zero-shot voice cloning."""
        return self.current_model_type in (MODEL_VIENEU, MODEL_OMNIVOICE)

    # ─── Model download checks ──────────────────────────────────────────

    def is_model_downloaded(self) -> bool:
        """Check if local model files exist for the current model type."""
        return self.model_manager.is_tts_model_downloaded(self.current_model_type)

    def ensure_model_downloaded(self, progress_callback=None) -> bool:
        """Download model files if needed into models/ and initialize into memory immediately."""
        self.model_manager.ensure_tts_model(self.current_model_type, progress_callback)
        # Tự động khởi động model để sẵn sàng dùng luôn ngay sau khi tải xong
        if progress_callback:
            progress_callback(90, f"Đang khởi động mô hình {self.current_model_type}...")
        self.load_model(progress_callback)
        if progress_callback:
            progress_callback(100, f"Mô hình {self.current_model_type} đã sẵn sàng!")
        return True

    # ─── Model loading ──────────────────────────────────────────────────

    def load_model(self, progress_callback=None) -> bool:
        """Load the current model type lazily with thread safety."""
        if self._is_loaded and self._engine is not None:
            return True

        with self._lock:
            if self._is_loaded and self._engine is not None:
                return True
            try:
                loader = {
                    MODEL_VIENEU: self._load_vieneu,
                    MODEL_OMNIVOICE: self._load_omnivoice,
                }[self.current_model_type]
                loader(progress_callback)
                self._is_loaded = True
                return True
            except Exception as e:
                logger.error(f"Failed to load {self.current_model_type} model: {e}")
                self._is_loaded = False
                self._engine = None
                raise

    def _load_vieneu(self, progress_callback=None) -> None:
        self.model_manager.ensure_vieneu_model(progress_callback=progress_callback)
        from vieneu import Vieneu
        kwargs: Dict[str, Any] = {"mode": self.mode}
        if self.model_manager.vieneu_onnx_dir.exists():
            kwargs["onnx_dir"] = str(self.model_manager.vieneu_onnx_dir.resolve())
        if self.model_manager.vieneu_dir.exists():
            kwargs["backbone_repo"] = str(self.model_manager.vieneu_dir.resolve())
        if self.model_manager.codec_dir.exists():
            kwargs["codec_dir"] = str(self.model_manager.codec_dir.resolve())
        self._engine = Vieneu(**kwargs)
        if hasattr(self._engine, "sample_rate") and self._engine.sample_rate:
            self.sample_rate = self._engine.sample_rate

    def _load_omnivoice(self, progress_callback=None) -> None:
        self.model_manager.ensure_omnivoice_model(progress_callback=progress_callback)
        if progress_callback:
            progress_callback(95, "Đang khởi tạo model...")
        from omnivoice import OmniVoice
        self._engine = OmniVoice.from_pretrained(str(self.model_manager.omnivoice_dir.resolve()))
        self._engine.eval()
        self.sample_rate = OMNIVOICE_SAMPLE_RATE

    # ─── Voice presets ──────────────────────────────────────────────────

    @staticmethod
    def _format_vieneu_display_name(name: str, desc: str = "", gender: str = "") -> str:
        """Format VieNeu voice display: 'Tên - Giới tính - Miền Bắc / Nam' (e.g. 'Phạm Tuyên - Nam - Miền Bắc')."""
        parts = [p.strip() for p in desc.split("·") if p.strip()] if desc else []
        g = ""
        if parts and parts[0] in ("Nam", "Nữ"):
            g = parts[0]
        elif gender:
            g_low = gender.strip().lower()
            if g_low in ("nam", "male"):
                g = "Nam"
            elif g_low in ("nữ", "nu", "female"):
                g = "Nữ"
            else:
                g = gender.strip()

        r = ""
        if len(parts) >= 2:
            r = parts[1].strip()
        elif "Bắc" in desc:
            r = "Bắc"
        elif "Nam" in desc:
            r = "Nam"
        elif "Trung" in desc:
            r = "Trung"

        if r and not r.startswith("Miền"):
            r = f"Miền {r}"

        elements = [name]
        if g:
            elements.append(g)
        if r:
            elements.append(r)
        return " - ".join(elements)

    def _load_cached_preset_voices(self) -> None:
        """Load preset voice list based on current model type."""
        if self.current_model_type == MODEL_OMNIVOICE:
            self._preset_voices = list(OMNIVOICE_PRESETS)
            return

        # VieNeu: try reading from package assets
        self._preset_voices = []
        try:
            import vieneu
            asset_dir = Path(vieneu.__file__).parent / "assets"
            turbo_json = asset_dir / "voices_v3_turbo.json"
            base_json = asset_dir / "voices.json"
            target_json = turbo_json if turbo_json.exists() else base_json
            if target_json.exists():
                data = json.loads(target_json.read_text(encoding="utf-8"))
                presets = data.get("presets", {})
                self._preset_voices = [
                    {
                        "id": name,
                        "label": self._format_vieneu_display_name(name, info.get("description", ""), info.get("gender", "")),
                        "description": info.get("description", ""),
                        "gender": info.get("gender", ""),
                    }
                    for name, info in presets.items()
                ]
        except Exception as e:
            logger.warning(f"Could not load pre-cached voices from assets: {e}")

        if not self._preset_voices:
            fallback_data = [
                ("Trúc Ly", "Nữ", "Bắc"),
                ("Phạm Tuyên", "Nam", "Bắc"),
                ("Thái Sơn", "Nam", "Nam"),
                ("Xuân Vĩnh", "Nam", "Bắc"),
                ("Thanh Bình", "Nam", "Bắc"),
                ("Minh Đức", "Nam", "Bắc"),
                ("Ngọc Linh", "Nữ", "Bắc"),
                ("Đoan Trang", "Nữ", "Bắc"),
                ("Mai Anh", "Nữ", "Bắc"),
                ("Thục Đoan", "Nữ", "Nam"),
            ]
            self._preset_voices = [
                {
                    "id": name,
                    "label": f"{name} - {g} - Miền {r}",
                    "description": f"{g} · {r}",
                    "gender": g,
                }
                for name, g, r in fallback_data
            ]

    def list_preset_voices(self) -> List[Dict[str, str]]:
        """Return preset voice metadata list for UI selectors."""
        return self._preset_voices

    # ─── Unload ─────────────────────────────────────────────────────────

    def unload_model(self) -> None:
        """Release TTS model resources."""
        with self._lock:
            if self._engine is not None:
                if hasattr(self._engine, "close"):
                    try:
                        self._engine.close()
                    except Exception:
                        pass
                del self._engine
            self._engine = None
            self._is_loaded = False
            import gc
            gc.collect()

    # ─── Synthesis ──────────────────────────────────────────────────────

    @staticmethod
    def _prepare_reference_audio(ref_path: Path) -> Path:
        """Ensure reference audio is in a format supported by engines, converting .m4a if needed."""
        if ref_path.suffix.lower() == ".m4a":
            import av
            cached_wav = OUTPUTS_DIR / f"_clone_{ref_path.stem}.wav"
            if cached_wav.exists() and cached_wav.stat().st_mtime >= ref_path.stat().st_mtime:
                return cached_wav
            container = av.open(str(ref_path))
            stream = container.streams.audio[0]
            frames = []
            for frame in container.decode(stream):
                frames.append(frame.to_ndarray())
            container.close()
            audio = np.concatenate(frames, axis=1)
            audio_out = audio.T if audio.ndim == 2 else audio
            sf.write(str(cached_wav), audio_out, stream.rate)
            return cached_wav
        return ref_path

    def synthesize(
        self,
        text: str,
        voice_ref: Optional[str] = None,
        speed: float = 1.0,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Synthesize text to speech with custom speed. Dispatches to the current model's inference method."""
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Văn bản cần đọc không được để trống.")

        self.load_model(progress_callback=progress_callback)
        if self._engine is None:
            raise RuntimeError("TTS engine chưa được khởi tạo.")

        if progress_callback:
            progress_callback(0, "Đang xử lý tạo giọng nói...")

        dispatcher = {
            MODEL_VIENEU: self._synthesize_vieneu,
            MODEL_OMNIVOICE: self._synthesize_omnivoice,
        }[self.current_model_type]

        start_time = time.time()
        raw_audio, sr, voice_desc = dispatcher(clean_text, voice_ref, speed=speed)
        elapsed = time.time() - start_time

        # Normalize to float32
        if not isinstance(raw_audio, np.ndarray):
            raw_audio = np.asarray(raw_audio, dtype=np.float32)
        elif raw_audio.dtype != np.float32:
            raw_audio = raw_audio.astype(np.float32)

        duration_sec = len(raw_audio) / float(sr) if sr > 0 else 0.0

        # timestamp_str = time.strftime("%Y%m%d_%H%M%S") 
        out_path = OUTPUTS_DIR / "sample.wav" #f"tts_{timestamp_str}.wav"
        sf.write(str(out_path), raw_audio, sr)

        return {
            "audio": raw_audio,
            "sample_rate": sr,
            "output_path": out_path,
            "duration": duration_sec,
            "elapsed_time": elapsed,
            "text": clean_text,
            "voice": voice_desc,
            "speed": speed,
        }

    def infer(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Convenience inference method: audio = tts.infer(text, voice="...", speed=0.75)."""
        return self.synthesize(text=text, voice_ref=voice, speed=speed, **kwargs)

    def _synthesize_vieneu(self, text: str, voice_ref: Optional[str], speed: float = 1.0) -> tuple:
        """VieNeu inference: configure speed directly in infer(..., speed=speed)."""
        kwargs: Dict[str, Any] = {"text": text, "speed": speed}
        ref_target = voice_ref or DEFAULT_VOICE

        if Path(ref_target).exists():
            ref_path = Path(ref_target).resolve()
            actual = self._prepare_reference_audio(ref_path)
            kwargs["ref_audio"] = str(actual)
            voice_desc = f"Clone ({ref_path.name})"
        else:
            kwargs["voice"] = ref_target
            voice_desc = ref_target

        with self._lock:
            raw_audio = self._engine.infer(**kwargs)

        sr = getattr(self._engine, "sample_rate", self.sample_rate)
        return raw_audio, sr, voice_desc

    def _synthesize_omnivoice(self, text: str, voice_ref: Optional[str], speed: float = 1.0) -> tuple:
        """OmniVoice inference: configure speed directly in generate(..., speed=speed)."""
        if not voice_ref or not Path(voice_ref).exists():
            raise ValueError(
                "Mô hình OmniVoice yêu cầu tệp âm thanh mẫu để nhân bản giọng nói (Voice Clone).\n"
                "Vui lòng nhấn vào nút 'Voice Clone' để chọn tệp âm thanh mẫu (.wav, .mp3, .m4a)."
            )

        ref_path = Path(voice_ref).resolve()
        actual = self._prepare_reference_audio(ref_path)
        kwargs: Dict[str, Any] = {
            "text": text,
            "ref_audio": str(actual),
            "speed": speed,
        }
        voice_desc = f"Clone ({ref_path.name})"

        with self._lock:
            result = self._engine.generate(**kwargs)

        raw_audio = np.concatenate(result) if len(result) > 1 else result[0]
        return raw_audio, OMNIVOICE_SAMPLE_RATE, voice_desc
