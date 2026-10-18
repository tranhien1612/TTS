import contextlib
import os
import sys
import logging
from pathlib import Path
from typing import Callable, Optional, List, Tuple
from core.config import (
    MODELS_DIR,
    OMNIVOICE_REPO,
    OMNIVOICE_DIR,
    MODEL_VIENEU,
    MODEL_OMNIVOICE,
    ASSETS_DIR,
)

logger = logging.getLogger(__name__)

SKETCH_REPO = "skytnt/anime-seg"


@contextlib.contextmanager
def _temp_online_env():
    """Temporarily allow outgoing HuggingFace traffic during model downloads."""
    keys = ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"]
    saved = {k: os.environ.get(k) for k in keys}
    try:
        for k in keys:
            os.environ[k] = "0"
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

# Hugging Face Repositories
VIENEU_REPO = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"

# Files required for VieNeu TTS ONNX inference
VIENEU_GRAPH_FILES = [
    "config.json",
    "tokenizer.json",
    "vieneu_prefill.onnx",
    "vieneu_decode_step.onnx",
    "vieneu_acoustic_cached.onnx",
    "vieneu_backbone_shared.data",
    "vieneu_v3_heads.npz",
]

VIENEU_ROOT_FILES = [
    "config.json",
    "denoiser.onnx",
    "speaker_encoder.onnx",
]

CODEC_FILES = [
    "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_decode_full.onnx",
    "moss_audio_tokenizer_decode_shared.data",
    "moss_audio_tokenizer_decode_step.onnx",
    "moss_audio_tokenizer_encode.onnx",
    "moss_audio_tokenizer_encode.data",
]


class ModelManager:
    """Manages checking, downloading, and verifying local model weights in models/."""

    def __init__(self, base_models_dir: Path = MODELS_DIR):
        self.models_dir = Path(base_models_dir)
        self.vieneu_dir = self.models_dir / "vieneu"
        self.vieneu_onnx_dir = self.vieneu_dir / "onnx_update"
        self.codec_dir = self.models_dir / "codec"
        self.whisper_dir = self.models_dir / "whisper-large-v3-turbo"
        self.omnivoice_dir = self.models_dir / "omnivoice"
        self.sketch_dir = self.models_dir / "v181d"

        # Ensure directories exist
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.vieneu_dir.mkdir(parents=True, exist_ok=True)
        self.vieneu_onnx_dir.mkdir(parents=True, exist_ok=True)
        self.codec_dir.mkdir(parents=True, exist_ok=True)
        self.whisper_dir.mkdir(parents=True, exist_ok=True)
        self.omnivoice_dir.mkdir(parents=True, exist_ok=True)
        self.sketch_dir.mkdir(parents=True, exist_ok=True)

    def _clean_stale_locks(self) -> None:
        """Purge orphaned .lock and .incomplete download cache files to prevent hangs."""
        for cache_dir in [self.vieneu_dir / ".cache", self.codec_dir / ".cache", self.omnivoice_dir / ".cache"]:
            if cache_dir.exists():
                for lock_file in cache_dir.rglob("*.lock"):
                    try:
                        lock_file.unlink()
                    except Exception:
                        pass
                for inc_file in cache_dir.rglob("*.incomplete"):
                    try:
                        inc_file.unlink()
                    except Exception:
                        pass

    def is_vieneu_downloaded(self) -> bool:
        """Check if all essential VieNeu model files exist locally in models/vieneu and models/codec."""
        return len(self.get_missing_files()) == 0

    def is_model_downloaded(self) -> bool:
        """Backward-compatible check for VieNeu model."""
        return self.is_vieneu_downloaded()

    def is_omnivoice_downloaded(self) -> bool:
        """Check if OmniVoice model weights exist locally in models/omnivoice."""
        if not (self.omnivoice_dir / "config.json").is_file():
            return False
        if not (self.omnivoice_dir / "model.safetensors").is_file():
            return False
        if not (self.omnivoice_dir / "audio_tokenizer" / "model.safetensors").is_file():
            return False
        return True

    def is_tts_model_downloaded(self, model_type: str = MODEL_VIENEU) -> bool:
        """Check whether local weights for the given TTS model type exist in models/."""
        if model_type == MODEL_VIENEU:
            return self.is_vieneu_downloaded()
        elif model_type == MODEL_OMNIVOICE:
            return self.is_omnivoice_downloaded()
        return False

    def get_missing_files(self) -> List[Tuple[str, str, Optional[str], Path]]:
        """Return list of (repo, filename, subfolder, destination_dir) for missing VieNeu files."""
        missing = []

        # Graph files in onnx_update
        for fn in VIENEU_GRAPH_FILES:
            if not (self.vieneu_onnx_dir / fn).is_file():
                missing.append((VIENEU_REPO, fn, "onnx_update", self.vieneu_dir))

        # Root files in vieneu
        for fn in VIENEU_ROOT_FILES:
            if not (self.vieneu_dir / fn).is_file():
                missing.append((VIENEU_REPO, fn, None, self.vieneu_dir))

        # Codec files
        for fn in CODEC_FILES:
            if not (self.codec_dir / fn).is_file():
                missing.append((CODEC_REPO, fn, None, self.codec_dir))

        return missing

    def ensure_vieneu_model(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Verify VieNeu model files; download any missing files into the models/ folder."""
        missing = self.get_missing_files()
        if not missing:
            return True

        self._clean_stale_locks()
        from huggingface_hub import hf_hub_download

        total = len(missing)
        with _temp_online_env():
            for idx, (repo, fn, subfolder, dest) in enumerate(missing, start=1):
                percent = int(((idx - 1) / total) * 100)
                msg = f"Đang tải {fn} ({idx}/{total})..."
                logger.info(msg)
                if progress_callback:
                    progress_callback(percent, msg)

                try:
                    hf_hub_download(
                        repo_id=repo,
                        filename=fn,
                        subfolder=subfolder,
                        local_dir=str(dest),
                        etag_timeout=15,
                    )
                except Exception as e:
                    # If optional helper fails (like denoiser on connection drop), log warning
                    if fn in ["denoiser.onnx", "codec_browser_onnx_meta.json"]:
                        logger.warning(f"Bỏ qua tệp tùy chọn {fn}: {e}")
                        continue
                    raise RuntimeError(f"Lỗi tải tệp mô hình {fn}: {e}") from e

        if progress_callback:
            progress_callback(100, "Đã tải xong toàn bộ mô hình VieNeu!")

        return True

    def ensure_model(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Backward-compatible ensure for VieNeu."""
        return self.ensure_vieneu_model(progress_callback)

    def ensure_omnivoice_model(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Download OmniVoice model files into models/omnivoice/."""
        if self.is_omnivoice_downloaded():
            return True

        self._clean_stale_locks()
        if progress_callback:
            progress_callback(10, "Đang tải mô hình OmniVoice...")

        from huggingface_hub import snapshot_download
        try:
            with _temp_online_env():
                snapshot_download(
                    repo_id=OMNIVOICE_REPO,
                    local_dir=str(self.omnivoice_dir),
                    etag_timeout=30,
                )
        except Exception as e:
            raise RuntimeError(f"Lỗi tải mô hình OmniVoice: {e}") from e

        if progress_callback:
            progress_callback(100, "Đã tải xong mô hình OmniVoice.")
        return True

    def ensure_tts_model(self, model_type: str = MODEL_VIENEU, progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Download the requested TTS model into models/ directory."""
        if model_type == MODEL_VIENEU:
            return self.ensure_vieneu_model(progress_callback)
        elif model_type == MODEL_OMNIVOICE:
            return self.ensure_omnivoice_model(progress_callback)
        return False

    def is_whisper_downloaded(self) -> bool:
        """Check if Whisper Large-v3-Turbo model files exist locally in models/."""
        if not (self.whisper_dir / "model.bin").is_file():
            return False
        if not (self.whisper_dir / "config.json").is_file():
            return False
        return True

    def ensure_whisper_model(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Verify Whisper Large-v3-Turbo files; download if missing."""
        if self.is_whisper_downloaded():
            return True

        self._clean_stale_locks()
        if progress_callback:
            progress_callback(10, "Đang tải mô hình Whisper...")

        from faster_whisper.utils import download_model
        with _temp_online_env():
            download_model(
                "large-v3-turbo",
                output_dir=str(self.whisper_dir),
            )

        if self.is_whisper_downloaded():
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_DATASETS_OFFLINE"] = "1"

        if progress_callback:
            progress_callback(100, "Đã tải xong mô hình Whisper.")
        return True

    def is_sketch_downloaded(self) -> bool:
        """Check if SkyTNT Anime-Seg model checkpoint exists locally."""
        if (self.sketch_dir / "model.safetensors").is_file():
            return True
        if (ASSETS_DIR / "v181d" / "model.safetensors").is_file():
            return True
        return False

    def ensure_sketch_model(self, progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Download SkyTNT Anime-Seg model checkpoint if missing."""
        if self.is_sketch_downloaded():
            return True

        self._clean_stale_locks()
        if progress_callback:
            progress_callback(10, "Đang tải mô hình video vẽ tay (anime-seg)...")

        from huggingface_hub import hf_hub_download
        with _temp_online_env():
            hf_hub_download(
                repo_id=SKETCH_REPO,
                filename="model.safetensors",
                local_dir=str(self.sketch_dir),
                etag_timeout=30,
            )

        if progress_callback:
            progress_callback(100, "Đã tải xong mô hình video vẽ tay.")
        return True
