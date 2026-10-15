"""Build script to compile Neu Audio Studio into a lightweight Windows executable (.exe).

Key requirements:
1. All generated files (spec, work/temp, dist/exe) are strictly contained inside the 'build/' folder.
2. Model weights in 'models/' are strictly excluded to keep the executable lightweight.
3. Models will be downloaded on-demand when the user executes a feature at runtime.
4. Supports both directory mode (--onedir, default for instant startup) and single file mode (--onefile).
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "build"
WORK_DIR = BUILD_DIR / "work"
DIST_DIR = BUILD_DIR / "dist"
SPEC_FILE = BUILD_DIR / "AudioStudio.spec"
LEGACY_DIST = ROOT_DIR / "dist"
LEGACY_SPEC = ROOT_DIR / "AudioStudio.spec"
ICON_PATH = ROOT_DIR / "assets" / "icons" / "app_icon.ico"
MAIN_SCRIPT = ROOT_DIR / "main.py"


def clean_previous_builds():
    """Remove previous build artifacts to ensure all outputs are fresh inside build/."""
    print("[-] Don dep cac tep build truoc do...")
    for path in [BUILD_DIR, LEGACY_DIST]:
        if path.exists():
            try:
                shutil.rmtree(path, ignore_errors=True)
                print(f"    Da xoa: {path}")
            except Exception as e:
                print(f"    Canh bao: Khong the xoa {path}: {e}")

    for spec_path in [SPEC_FILE, LEGACY_SPEC]:
        if spec_path.exists():
            try:
                spec_path.unlink()
                print(f"    Da xoa: {spec_path}")
            except Exception as e:
                print(f"    Canh bao: Khong the xoa {spec_path}: {e}")


def ensure_pyinstaller():
    """Verify PyInstaller is installed, installing if missing."""
    try:
        import PyInstaller
        print(f"[+] Found PyInstaller version {PyInstaller.__version__}")
    except ImportError:
        print("[!] PyInstaller is not installed. Installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_executable(onefile: bool = False):
    """Run PyInstaller with all outputs directed into build/."""
    ensure_pyinstaller()
    clean_previous_builds()

    # Ensure build directories exist
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    if not ICON_PATH.exists():
        print(f"[!] Warning: Icon not found at {ICON_PATH}")

    print("\n" + "=" * 60)
    print(" " * 15 + "Neu Audio Studio Build")
    print("=" * 60)
    print(f"Main script:       {MAIN_SCRIPT}")
    print(f"Packaging mode:    {'Single Executable (--onefile)' if onefile else 'Application Folder (--onedir)'}")
    print(f"Build root dir:    {BUILD_DIR}")
    print(f"Executable dir:    {DIST_DIR}")
    print(f"Application icon:  {ICON_PATH}")
    print(f"Excluded:          models/ (downloaded automatically at runtime)")
    print("=" * 60 + "\n")

    # Base PyInstaller command with all paths directed inside build/
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(MAIN_SCRIPT),
        "--name=AudioStudio",
        "--noconsole",
        "--clean",
        "-y",
        "--specpath",
        str(BUILD_DIR),
        "--workpath",
        str(WORK_DIR),
        "--distpath",
        str(DIST_DIR),
    ]

    # Packaging mode
    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Icon
    if ICON_PATH.exists():
        cmd.extend(["--icon", str(ICON_PATH)])

    # Bundle assets folder (excluding models/)
    # Syntax for Windows PyInstaller --add-data: "src;dest"
    assets_dir = ROOT_DIR / "assets"
    if assets_dir.exists():
        cmd.extend(["--add-data", f"{assets_dir};assets"])

    # Collect necessary packages and their dynamic libraries / data
    collect_packages = [
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",
        "vieneu",
        "sea_g2p",
        "tokenizers",
        "torch",
    ]
    for pkg in collect_packages:
        cmd.extend(["--collect-all", pkg])

    # Hidden imports
    hidden_imports = [
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "huggingface_hub",
        "numpy",
        "sounddevice",
        "soundfile",
        "core",
        "core.config",
        "core.model_manager",
        "core.worker",
        "engines",
        "engines.base_engine",
        "engines.tts_engine",
        "engines.stt_engine",
        "ui",
        "ui.styles",
        "ui.main_window",
        "ui.views.tts_view",
        "ui.views.stt_view",
    ]
    for hi in hidden_imports:
        cmd.extend(["--hidden-import", hi])

    # Strictly exclude unused massive frameworks to prevent RAM bloat and keep .exe lightweight
    exclude_modules = [
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "tensorboard",
        "matplotlib",
        "scipy",
        "IPython",
        "notebook",
        "jupyter",
        "pytest",
        "unittest",
        "tkinter",
    ]
    for ex in exclude_modules:
        cmd.extend(["--exclude-module", ex])

    print("Running PyInstaller...")
    print(" ".join(cmd[:12]) + " ...")

    env = os.environ.copy()
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), env=env)

    if result.returncode == 0:
        print("\n" + "=" * 60)
        print(" BUILD SUCCEEDED!")
        print("=" * 60)
        if onefile:
            exe_path = DIST_DIR / "AudioStudio.exe"
            print(f"Executable file:   {exe_path}")
        else:
            exe_dir = DIST_DIR / "AudioStudio"
            exe_path = exe_dir / "AudioStudio.exe"
            print(f"App directory:     {exe_dir}")
            print(f"Executable file:   {exe_path}")
        print(f"All generated files are strictly saved in: {BUILD_DIR}")
        print("\nNote: AI models are NOT bundled into this build.")
        print("When you launch AudioStudio.exe, models will download on-demand into 'models/' next to the .exe.")
        print("=" * 60 + "\n")
        return True
    else:
        print(f"\n[!] Build failed with exit code {result.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Build AudioStudio into a Windows executable.")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single standalone .exe file instead of a folder distribution (--onedir).",
    )
    args = parser.parse_args()

    success = build_executable(onefile=args.onefile)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
