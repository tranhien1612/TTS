import os
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

MODELS_DIR = BASE_DIR / "models"
OUTPUTS_DIR = BASE_DIR / "outputs"
EXAMPLES_DIR = BASE_DIR / "examples"

ASSETS_DIR = None
for candidate in [
    BUNDLE_DIR / "assets",
    BASE_DIR / "assets",
    BASE_DIR / "_internal" / "assets",
]:
    if candidate.exists():
        ASSETS_DIR = candidate
        break
if ASSETS_DIR is None:
    ASSETS_DIR = BASE_DIR / "assets"

ICONS_DIR = ASSETS_DIR / "icons"
FFMPEG_BIN_DIR = ASSETS_DIR / "ffmpeg_bin"

# Force native Windows Media Foundation backend for Qt Multimedia on Windows
# Prevents crash/corruption with external FFmpeg binaries and DLLs
if sys.platform == "win32":
    os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

FFMPEG_EXE = FFMPEG_BIN_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
FFPROBE_EXE = FFMPEG_BIN_DIR / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
FFPLAY_EXE = FFMPEG_BIN_DIR / ("ffplay.exe" if sys.platform == "win32" else "ffplay")


def setup_ffmpeg_env() -> None:
    """Configure system environment to prioritize bundled assets/ffmpeg_bin for subprocesses."""
    if FFMPEG_BIN_DIR.exists():
        bin_str = str(FFMPEG_BIN_DIR)
        current_path = os.environ.get("PATH", "")
        paths = current_path.split(os.pathsep)
        if bin_str not in paths:
            os.environ["PATH"] = bin_str + os.pathsep + current_path
        if FFMPEG_EXE.exists():
            os.environ["FFMPEG_BINARY"] = str(FFMPEG_EXE)


setup_ffmpeg_env()


APP_ICON_PATH = ICONS_DIR / "app_icon.ico"
APP_ICON_PNG = ICONS_DIR / "app_icon.png"

# Ensure runtime directories exist
MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)

# Application metadata
APP_NAME = "Audio Studio"
APP_VERSION = "1.0.0"

# TTS Engine Configuration
DEFAULT_MODEL_MODE = "v3turbo"
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_VOICE = "Trúc Ly"

# Supported TTS model types
MODEL_VIENEU = "vieneu"
MODEL_OMNIVOICE = "omnivoice"
DEFAULT_TTS_MODEL = MODEL_VIENEU

# OmniVoice Configuration
OMNIVOICE_REPO = "k2-fsa/OmniVoice"
OMNIVOICE_DIR = MODELS_DIR / "omnivoice"
OMNIVOICE_DIR.mkdir(parents=True, exist_ok=True)
OMNIVOICE_SAMPLE_RATE = 24000

# Audio format filters for QFileDialog
SUPPORTED_AUDIO_EXTENSIONS = [".wav", ".mp3", ".flac", ".ogg", ".m4a"]
AUDIO_FILE_FILTER = "Tệp âm thanh (*.wav *.mp3 *.flac *.ogg *.m4a);;Tất cả tệp (*.*)"

# Video format filters for QFileDialog
SUPPORTED_VIDEO_EXTENSIONS = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"]
VIDEO_FILE_FILTER = "Tệp video (*.mp4 *.mkv *.avi *.mov *.webm *.flv);;Tất cả tệp (*.*)"

# STT Engine Configuration (Whisper Large-v3-Turbo)
WHISPER_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
WHISPER_DIR = MODELS_DIR / "whisper-large-v3-turbo"
WHISPER_DIR.mkdir(parents=True, exist_ok=True)
WHISPER_DEFAULT_LANGUAGE = "vi"

# Translation Engine Configuration (CTranslate2 NLLB-200)
NLLB_REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
NLLB_DIR = MODELS_DIR / "nllb-200-distilled-600M-ct2-int8"
NLLB_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_outputs_dir() -> int:
    """Clear all old files and data from outputs/ directory on startup to prevent disk bloat.

    Returns the number of deleted items.
    """
    import shutil
    deleted_count = 0
    if not OUTPUTS_DIR.exists():
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        return 0

    for item in OUTPUTS_DIR.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink(missing_ok=True)
                deleted_count += 1
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
                deleted_count += 1
        except Exception:
            pass

    return deleted_count


def get_ffmpeg_path() -> str:
    """Return path to ffmpeg binary, prioritizing bundled assets/ffmpeg_bin."""
    if FFMPEG_EXE.exists():
        return str(FFMPEG_EXE)
    configured = os.environ.get("FFMPEG_BINARY")
    if configured and Path(configured).exists():
        return configured
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    return "ffmpeg"


def get_ffprobe_path() -> str:
    """Return path to ffprobe binary, prioritizing bundled assets/ffmpeg_bin."""
    if FFPROBE_EXE.exists():
        return str(FFPROBE_EXE)
    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        return system_ffprobe
    return "ffprobe"


def get_subprocess_no_window_kwargs() -> dict:
    """Return subprocess flags to prevent creating or showing a terminal/console window on Windows."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return kwargs


def force_kill_app() -> None:
    """Force kill the application and any spawned child processes (FFmpeg, workers) immediately."""
    try:
        import psutil
        parent = psutil.Process(os.getpid())
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(os.getpid())],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
    finally:
        os._exit(0)





