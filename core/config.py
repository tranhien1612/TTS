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

ASSETS_DIR = BUNDLE_DIR / "assets" if (BUNDLE_DIR / "assets").exists() else BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
EXAMPLES_DIR = ASSETS_DIR / "examples"

APP_ICON_PATH = ICONS_DIR / "app_icon.ico"
APP_ICON_PNG = ICONS_DIR / "app_icon.png"

# Ensure runtime directories exist
MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)
EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

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

# STT Engine Configuration (Whisper Large-v3-Turbo)
WHISPER_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
WHISPER_DIR = MODELS_DIR / "whisper-large-v3-turbo"
WHISPER_DIR.mkdir(parents=True, exist_ok=True)
WHISPER_DEFAULT_LANGUAGE = "vi"


