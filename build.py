"""Build script — Neu Audio Studio (VieNeu + OmniVoice + Whisper).

Fix v5:
- Bỏ --optimize=2 (gây NameError 'name' is not defined trong OmniVoice)
- Thêm --collect-all omnivoice
- Thêm omnivoice.* vào hidden imports

Cách dùng:
    python build.py              # onedir
    python build.py --onefile    # single file .exe
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ============================================================
#  ĐƯỜNG DẪN
# ============================================================
ROOT_DIR    = Path(__file__).resolve().parent
BUILD_DIR   = ROOT_DIR / "build"
WORK_DIR    = BUILD_DIR / "work"
DIST_DIR    = BUILD_DIR / "dist"
SPEC_FILE   = BUILD_DIR / "AudioStudio.spec"

LEGACY_DIST = ROOT_DIR / "dist"
LEGACY_SPEC = ROOT_DIR / "AudioStudio.spec"

ICON_PATH   = ROOT_DIR / "assets" / "icons" / "app_icon.ico"
MAIN_SCRIPT = ROOT_DIR / "main.py"
RTHOOK      = ROOT_DIR / "core" / "pyinstaller_rthook.py"


# ============================================================
#  DỌN DẸP
# ============================================================
def clean_previous_builds():
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "AudioStudio.exe"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    print("[-] Dọn dẹp build cũ...")
    for path in [BUILD_DIR, LEGACY_DIST]:
        if path.exists():
            try:
                shutil.rmtree(path, ignore_errors=True)
                print(f"    Đã xóa: {path}")
            except Exception as e:
                print(f"    [!] Bỏ qua dọn dẹp {path}: {e}")

    for spec in [SPEC_FILE, LEGACY_SPEC]:
        if spec.exists():
            try:
                spec.unlink()
                print(f"    Đã xóa: {spec}")
            except Exception:
                pass


def ensure_pyinstaller():
    try:
        import PyInstaller
        print(f"[+] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[!] Cài đặt PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


# ============================================================
#  BUILD
# ============================================================
def build_executable(onefile: bool = False):
    ensure_pyinstaller()
    clean_previous_builds()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    mode = "onefile" if onefile else "onedir"

    print("\n" + "=" * 60)
    print(f"  Neu Audio Studio Build — {mode}")
    print("=" * 60)
    print(f"  Main script:  {MAIN_SCRIPT}")
    print(f"  Build dir:    {BUILD_DIR}")
    print(f"  Dist dir:     {DIST_DIR}")
    print(f"  Icon:         {ICON_PATH}")
    print(f"  Runtime hook: {RTHOOK}")
    print(f"  Models:       KHÔNG bundle")
    print("=" * 60 + "\n")

    # ============================================================
    #  BASE COMMAND
    #  LƯU Ý: ĐÃ BỎ --optimize=2 (gây lỗi NameError trong OmniVoice)
    # ============================================================
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(MAIN_SCRIPT),
        "--name=AudioStudio",
        "--noconsole",
        "--clean",
        "-y",
        "--specpath", str(BUILD_DIR),
        "--workpath", str(WORK_DIR),
        "--distpath", str(DIST_DIR),
        # "--optimize=2",    ← BỎ để tránh strip code động
        "--log-level=WARN",
    ]

    cmd.append("--onefile" if onefile else "--onedir")

    # ============================================================
    #  RUNTIME HOOK
    # ============================================================
    if RTHOOK.exists():
        cmd.extend(["--runtime-hook", str(RTHOOK)])
        print(f"[+] Runtime hook: {RTHOOK}")
    else:
        print(f"[!] CẢNH BÁO: Không tìm thấy runtime hook: {RTHOOK}")

    # ============================================================
    #  ICON
    # ============================================================
    if ICON_PATH.exists():
        cmd.extend(["--icon", str(ICON_PATH)])

    # ============================================================
    #  ASSETS, FFMPEG_BIN & VENDOR RUNTIME
    # ============================================================
    assets_dir = ROOT_DIR / "assets"
    if assets_dir.exists():
        cmd.extend(["--add-data", f"{assets_dir};assets"])

    ffmpeg_bin_dir = assets_dir / "ffmpeg_bin"
    if ffmpeg_bin_dir.exists():
        # Ensure FFmpeg binaries and DLLs are collected for both onefile and onedir modes
        cmd.extend(["--add-data", f"{ffmpeg_bin_dir};assets/ffmpeg_bin"])
        for bin_file in ffmpeg_bin_dir.glob("*.exe"):
            cmd.extend(["--add-binary", f"{bin_file};assets/ffmpeg_bin"])
        for dll_file in ffmpeg_bin_dir.glob("*.dll"):
            cmd.extend(["--add-binary", f"{dll_file};assets/ffmpeg_bin"])
        print(f"[+] Đã cấu hình bundle FFmpeg từ: {ffmpeg_bin_dir}")

    vendor_runtime_dir = ROOT_DIR / "vendor_runtime"
    if vendor_runtime_dir.exists():
        cmd.extend(["--add-data", f"{vendor_runtime_dir};vendor_runtime"])

    examples_dir = ROOT_DIR / "examples"
    if examples_dir.exists():
        cmd.extend(["--add-data", f"{examples_dir};examples"])

    # ============================================================
    #  FIX SETUPTOOLS JARACO.TEXT
    # ============================================================
    try:
        import setuptools._vendor.jaraco.text as jt
        lorem = Path(jt.__file__).parent / "Lorem ipsum.txt"
        if lorem.exists():
            cmd.extend(["--add-data", f"{lorem};setuptools/_vendor/jaraco/text"])
    except Exception:
        pass

    cmd.extend(["--collect-data", "setuptools"])

    # ============================================================
    #  PYQT6 — plugins
    # ============================================================
    cmd.extend(["--collect-data", "PyQt6"])

    # ============================================================
    #  TORCH + TORCHAUDIO — collect-all để tránh circular import
    # ============================================================
    cmd.extend(["--collect-all", "torch"])
    cmd.extend(["--collect-all", "torchaudio"])
    cmd.extend(["--collect-all", "torchvision"])

    # ============================================================
    #  OMNIVOICE — BẮT BUỘC để download model
    #  Dùng collect-all để lấy hết submodules + data + dynamic imports
    # ============================================================
    cmd.extend(["--collect-all", "omnivoice"])

    # ============================================================
    #  VIENEU — TTS + Voice Cloning
    # ============================================================
    cmd.extend(["--collect-all", "vieneu"])

    # ============================================================
    #  SEA G2P
    # ============================================================
    cmd.extend(["--collect-all", "sea_g2p"])

    # ============================================================
    #  FASTER WHISPER (STT)
    # ============================================================
    cmd.extend(["--collect-data", "faster_whisper"])

    # ============================================================
    #  ONNX RUNTIME
    # ============================================================
    cmd.extend(["--collect-binaries", "onnxruntime"])
    cmd.extend(["--collect-submodules", "onnxruntime.capi"])
    cmd.extend(["--collect-data", "onnxruntime"])

    # ============================================================
    #  CTranslate2
    # ============================================================
    cmd.extend(["--collect-binaries", "ctranslate2"])
    cmd.extend(["--collect-data", "ctranslate2"])

    # ============================================================
    #  Tokenizers / Transformers / HuggingFace / Safetensors
    # ============================================================
    cmd.extend(["--collect-binaries", "tokenizers"])
    cmd.extend(["--collect-data", "tokenizers"])
    cmd.extend(["--collect-data", "transformers"])
    cmd.extend(["--collect-data", "huggingface_hub"])
    cmd.extend(["--collect-submodules", "huggingface_hub"])
    cmd.extend(["--collect-binaries", "safetensors"])

    cmd.extend(["--collect-all", "mkl"])
    cmd.extend(["--collect-all", "intel-openmp"])
    # ============================================================
    #  HIDDEN IMPORTS
    # ============================================================
    hidden_imports = [
        # --- PyQt6 ---
        "PyQt6", "PyQt6.sip",
        "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
        "PyQt6.QtNetwork", "PyQt6.QtSvg", "PyQt6.QtSvgWidgets",
        "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",

        "core", "core.config", "core.model_manager", "core.worker", "core.handdraw",
        "engines", "engines.base_engine", "engines.tts_engine", "engines.stt_engine", "engines.sketch_engine",
        "ui", "ui.styles", "ui.main_window",
        "ui.views.tts_view", "ui.views.stt_view", "ui.views.sketch_view", "ui.views.settings_view",
        "ui.components.audio_player", "ui.components.card", "ui.components.voice_pill", "ui.components.video_player",

        # --- Audio ---
        "numpy", "sounddevice", "soundfile",

        # --- OmniVoice (BẮT BUỘC) ---
        "omnivoice",
        "omnivoice.models",
        "omnivoice.utils",
        "omnivoice.voice_clone",     # ← thêm các submodule bạn biết
        "omnivoice.tokenizer",

        # --- VieNeu ---
        "vieneu",
        "vieneu.tts",
        "vieneu.clone",              # ← voice cloning
        "vieneu.utils",

        # --- Sea G2P ---
        "sea_g2p",
        "sea_g2p.g2p",

        # --- STT ---
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",

        # --- ML stack ---
        "tokenizers", "transformers", "safetensors", "huggingface_hub",

        # --- Torch ---
        "torch", "torch.nn", "torch.autograd", "torch.nn.functional",
        "torch._C", "torch._dl", "torch.cuda", "torch.backends",
        "torch.distributed", "torch.distributed.rpc", "torch.distributed.rpc.internal",
        "torchaudio", "torchvision",

        # --- pycparser fix warning ---
        "pycparser",
        "pycparser.ply",

        "tbb", "tbb.pool", "mkl", "mkl_fft", "mkl_random",
    ]
    for hi in hidden_imports:
        cmd.extend(["--hidden-import", hi])

    # ============================================================
    #  EXCLUDES — KHÔNG exclude torch/omnivoice/vieneu
    # ============================================================
    exclude_modules = [
        "tensorflow", "tensorboard", "keras",
        "sklearn", "pandas",
        "matplotlib", "seaborn", "plotly",
        "IPython", "notebook", "jupyter", "nbconvert",
        "pytest",

        "tkinter", "wx", "kivy",
        "PyQt6.QtWebEngine",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "PyQt6.Qt3DCore",
        "PyQt6.Qt3DRender",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.QtCharts",
        "PyQt6.QtDataVisualization",
        "PyQt6.QtWebSockets",
        "PyQt6.QtWebChannel",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtDesigner",

        "nltk",
        "pygame",
        "yt_dlp",
        "moviepy",
    ]
    for ex in exclude_modules:
        cmd.extend(["--exclude-module", ex])

    # ============================================================
    #  CHẠY
    # ============================================================
    print("Chạy PyInstaller...")
    print(" ".join(cmd[:12]) + " ... (đã rút gọn)\n")

    result = subprocess.run(cmd, cwd=str(ROOT_DIR))

    if result.returncode != 0:
        print(f"\n[!] Build thất bại (exit code {result.returncode})")
        return False

    print("\n" + "=" * 60)
    print(" BUILD THÀNH CÔNG")
    print("=" * 60)

    if onefile:
        exe = DIST_DIR / "AudioStudio.exe"
        size = exe.stat().st_size / (1024 * 1024)
        print(f"  EXE:   {exe}")
        print(f"  Size:  {size:.1f} MB")
    else:
        exe_dir = DIST_DIR / "AudioStudio"
        exe = exe_dir / "AudioStudio.exe"

        # Ensure vendor_runtime and assets (including ffmpeg_bin) are directly accessible in dist
        for target_base in [exe_dir, exe_dir / "_internal"]:
            if target_base.exists():
                vr_target = target_base / "vendor_runtime"
                if not vr_target.exists() and vendor_runtime_dir.exists():
                    shutil.copytree(vendor_runtime_dir, vr_target, dirs_exist_ok=True)
                    print(f"[+] Đã sao chép vendor_runtime vào {vr_target}")

                assets_target = target_base / "assets"
                if assets_dir.exists():
                    shutil.copytree(assets_dir, assets_target, dirs_exist_ok=True)
                    print(f"[+] Đã sao chép assets (kèm ffmpeg_bin) vào {assets_target}")

                examples_target = target_base / "examples"
                if examples_dir.exists():
                    shutil.copytree(examples_dir, examples_target, dirs_exist_ok=True)
                    print(f"[+] Đã sao chép examples vào {examples_target}")

        total = sum(f.stat().st_size for f in exe_dir.rglob("*") if f.is_file())
        print(f"  Folder: {exe_dir}")
        print(f"  EXE:    {exe}")
        print(f"  Size:   {total / 1024 / 1024:.1f} MB")

    print(f"\n  Output: {BUILD_DIR}")
    print("\n  LƯU Ý:")
    print("  - Models KHÔNG bundle trong .exe")
    print("  - Lần chạy đầu, model tải về '<exe_dir>/models/'")
    print("=" * 60 + "\n")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true",
                        help="Đóng gói thành 1 file .exe duy nhất")
    args = parser.parse_args()
    sys.exit(0 if build_executable(onefile=args.onefile) else 1)


if __name__ == "__main__":
    main()