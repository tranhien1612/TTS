"""Sketch & Whiteboard Animation Engine for Neu Audio Studio.

Wraps the handdraw core library and v181d model to generate hand-drawn sketch videos
from static images, adhering to project settings and parameters.
"""
from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Callable, Optional, Union, Tuple, Dict, Any

import numpy as np
from PIL import Image

from core.config import OUTPUTS_DIR, ASSETS_DIR
from core.handdraw.settings import Settings


LOGGER = logging.getLogger("engines.sketch_engine")


class SketchEngine:
    """Hand-drawn whiteboard animation engine using core.handdraw and v181d assets."""

    def __init__(self) -> None:
        self.outputs_dir: Path = OUTPUTS_DIR
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.v181d_dir: Path = ASSETS_DIR / "v181d"

    @staticmethod
    def is_cuda_available() -> bool:
        """Check if CUDA GPU acceleration is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    @staticmethod
    def is_nvenc_available() -> bool:
        """Check if NVIDIA NVENC hardware encoder is likely available."""
        return SketchEngine.is_cuda_available()

    def is_assets_ready(self) -> bool:
        """Verify that required model weights and hand assets exist."""
        required = [
            self.v181d_dir / "color-hand-long.png",
            self.v181d_dir / "draw-hand-long.png",
        ]
        return all(p.exists() for p in required)

    def is_model_downloaded(self) -> bool:
        """Verify that required anime-seg / v181d model and hand assets exist."""
        from core.model_manager import ModelManager
        return ModelManager().is_sketch_downloaded() and self.is_assets_ready()

    def ensure_model_downloaded(self, progress_callback=None) -> bool:
        """Download sketch model if missing and initialize."""
        from core.model_manager import ModelManager
        res = ModelManager().ensure_sketch_model(progress_callback)
        self.load_model(progress_callback)
        return res

    def load_model(self, progress_callback=None) -> bool:
        """Pre-load ISNet subject segmentation model into memory."""
        try:
            if progress_callback:
                progress_callback(80, "Đang khởi tạo mô hình vẽ tay...")
            from core.handdraw.subject import _get_model
            _get_model("cpu")
            if progress_callback:
                progress_callback(100, "Mô hình video vẽ tay đã sẵn sàng!")
            return True
        except Exception as e:
            LOGGER.warning(f"Không thể pre-load model vẽ tay: {e}")
            return False

    def build_settings(
        self,
        duration: float = 10.0,
        fps: int = 30,
        device: str = "cpu",
        encoder: str = "cpu",
        width: int = 1920,
        height: int = 1080,
        **extra_kwargs: Any,
    ) -> Settings:
        """Map user UI configuration to a validated Settings object."""
        # 1. Normalize device ('cpu' or 'cuda')
        dev_upper = str(device).strip().upper()
        if dev_upper in ("GPU", "CUDA") and self.is_cuda_available():
            normalized_device = "cuda"
        else:
            normalized_device = "cpu"

        # 2. Normalize encoder ('cpu' or 'nvenc')
        # Note: 'nvenc' requires device == 'cuda'
        enc_upper = str(encoder).strip().upper()
        if ("NVENC" in enc_upper or enc_upper == "NVENC") and normalized_device == "cuda":
            normalized_encoder = "nvenc"
        else:
            normalized_encoder = "cpu"

        # 3. Clamp duration [0.1, 120.0] and fps [1, 60]
        safe_duration = max(0.1, min(120.0, float(duration)))
        safe_fps = max(1, min(60, int(fps)))

        # 4. Clamp width [64, 3840] and height [64, 2160] (ensure even integers)
        safe_width = max(64, min(3840, int(width) // 2 * 2))
        safe_height = max(64, min(2160, int(height) // 2 * 2))

        config_dict = {
            "duration": safe_duration,
            "fps": safe_fps,
            "device": normalized_device,
            "encoder": normalized_encoder,
            "width": safe_width,
            "height": safe_height,
        }

        # Merge with any extra overrides if provided
        for k, v in extra_kwargs.items():
            if hasattr(Settings, k):
                config_dict[k] = v

        settings = Settings(**config_dict)
        return settings.validate()

    def render(
        self,
        image_input: Union[Path, str, Image.Image, np.ndarray],
        duration: float = 10.0,
        fps: int = 30,
        device: str = "cpu",
        encoder: str = "cpu",
        width: int = 1920,
        height: int = 1080,
        output_dir: Optional[Union[Path, str]] = None,
        output_file: Optional[Union[Path, str]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        **extra_kwargs: Any,
    ) -> Tuple[Path, Optional[Dict[str, Any]]]:
        """Render a hand-drawn sketch video from an input image.

        Args:
            image_input: Image file path, PIL Image, or RGB uint8 numpy array.
            duration: Video length in seconds (default 10s).
            fps: Frame rate (default 30 fps).
            device: 'CPU' or 'GPU'.
            encoder: 'CPU H.264' or 'NVIDIA NVENC'.
            width: Maximum video width in px (default 1920).
            height: Maximum video height in px (default 1080).
            output_dir: Target output folder (default: core.config.OUTPUTS_DIR).
            output_file: Optional explicit target path for the rendered MP4.
            progress_callback: Optional function (fraction: 0.0..1.0, message: str) -> None.
            extra_kwargs: Additional parameters passed to Settings.

        Returns:
            Tuple of (output_video_path, render_report_dict)
        """
        # Load and convert image to RGB numpy array
        if isinstance(image_input, (str, Path)):
            input_path = Path(image_input)
            if not input_path.exists():
                raise FileNotFoundError(f"Không tìm thấy tệp ảnh: {input_path}")
            pil_img = Image.open(input_path).convert("RGB")
            img_np = np.array(pil_img, dtype=np.uint8)
        elif isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGB")
            img_np = np.array(pil_img, dtype=np.uint8)
        elif isinstance(image_input, np.ndarray):
            if image_input.ndim != 3 or image_input.shape[2] not in (3, 4):
                raise ValueError("Numpy image array phải có 3 hoặc 4 kênh màu (RGB/RGBA)")
            if image_input.shape[2] == 4:
                pil_img = Image.fromarray(image_input).convert("RGB")
                img_np = np.array(pil_img, dtype=np.uint8)
            else:
                img_np = image_input.astype(np.uint8)
        else:
            raise TypeError(f"Định dạng hình ảnh không được hỗ trợ: {type(image_input)}")

        # Construct validated settings
        settings = self.build_settings(
            duration=duration,
            fps=fps,
            device=device,
            encoder=encoder,
            width=width,
            height=height,
            **extra_kwargs,
        )

        target_dir = Path(output_dir) if output_dir else self.outputs_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Bắt đầu render video vẽ tay: duration=%.1fs, fps=%d, device=%s, encoder=%s",
            settings.duration, settings.fps, settings.device, settings.encoder,
        )

        # Progress callback adapter
        def _cb(fraction: float, description: str = "") -> None:
            if progress_callback:
                progress_callback(fraction, description)

        # Execute core render (lazy import to keep app startup fast)
        from core.handdraw.render import render_video
        video_path, report = render_video(
            img_np,
            settings,
            output_dir=str(target_dir),
            progress=_cb,
        )

        final_path = Path(video_path).resolve()

        # If a specific output_file was requested, move or copy the video there
        if output_file:
            desired_path = Path(output_file).resolve()
            desired_path.parent.mkdir(parents=True, exist_ok=True)
            if final_path != desired_path:
                shutil.copy2(final_path, desired_path)
                final_path = desired_path

        LOGGER.info("Render video vẽ tay hoàn tất: %s", final_path)
        return final_path, report
