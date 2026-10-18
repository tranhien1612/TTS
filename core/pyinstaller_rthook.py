"""PyInstaller runtime hook — chạy TRƯỚC main.py trong .exe.

Xử lý:
1. Fix sys.stdout/stderr = None (--noconsole)
2. Set HF_HOME, TRANSFORMERS_CACHE → model tải về <exe_dir>/models/
3. Set KMP_DUPLICATE_LIB_OK → tránh OMP Error #15
4. Tạo thư mục models/, logs/
5. Fix jaraco.text Lorem ipsum
6. multiprocessing.freeze_support()
"""

import os
import sys
from pathlib import Path


# ----------------------------------------------------------
#  1. FIX STREAMS
# ----------------------------------------------------------
class _NullWriter:
    name = "nul"
    mode = "w"
    encoding = "utf-8"
    errors = "replace"

    def write(self, s):
        return len(s) if s else 0

    def flush(self):
        pass

    def isatty(self):
        return False

    def writelines(self, lines):
        return sum(len(l) for l in lines)

    def fileno(self):
        raise OSError("Null stream has no fileno")


for name in ("stdout", "stderr", "__stdout__", "__stderr__"):
    if getattr(sys, name, None) is None:
        try:
            setattr(sys, name, open(os.devnull, "w",
                                    encoding="utf-8", errors="replace"))
        except Exception:
            setattr(sys, name, _NullWriter())

for name in ("stdin", "__stdin__"):
    if getattr(sys, name, None) is None:
        try:
            setattr(sys, name, open(os.devnull, "r",
                                    encoding="utf-8", errors="replace"))
        except Exception:
            setattr(sys, name, _NullWriter())

# Tắt progress bars (không có console)
os.environ["TQDM_DISABLE"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


# ----------------------------------------------------------
#  2. BASE DIR + CACHE PATHS
# ----------------------------------------------------------
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent  # dev mode


BASE_DIR = _get_base_dir()
MODELS_DIR = BASE_DIR / "models"

def _setup_cache_paths():
    hf_cache = MODELS_DIR / "hf"
    hub_cache = hf_cache / "hub"
    torch_cache = MODELS_DIR / "torch"

    for d in (MODELS_DIR, hf_cache, hub_cache, torch_cache):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # HuggingFace / Transformers
    os.environ["HF_HOME"] = str(hf_cache)
    os.environ["HF_HUB_CACHE"] = str(hub_cache)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hub_cache)
    os.environ["TRANSFORMERS_CACHE"] = str(hf_cache)

    # Torch
    os.environ["TORCH_HOME"] = str(torch_cache)


_setup_cache_paths()


# ----------------------------------------------------------
#  3. OMP FIX
# ----------------------------------------------------------
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ----------------------------------------------------------
#  4. FIX JARACO.TEXT
# ----------------------------------------------------------
def _fix_jaraco_lorem():
    try:
        if not getattr(sys, "frozen", False):
            return
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS))
        candidates.append(BASE_DIR)
        candidates.append(BASE_DIR / "_internal")

        for root in candidates:
            tdir = root / "setuptools" / "_vendor" / "jaraco" / "text"
            if tdir.exists():
                lfile = tdir / "Lorem ipsum.txt"
                if not lfile.exists():
                    lfile.write_text("Lorem ipsum dolor sit amet",
                                     encoding="utf-8")
    except Exception:
        pass


_fix_jaraco_lorem()


# ----------------------------------------------------------
#  5. MULTIPROCESSING
# ----------------------------------------------------------
try:
    import multiprocessing
    multiprocessing.freeze_support()
except Exception:
    pass


# ----------------------------------------------------------
#  6. FFMPEG BINARY SETUP & QT MEDIA BACKEND
# ----------------------------------------------------------
if sys.platform == "win32":
    os.environ.setdefault("QT_MEDIA_BACKEND", "windows")

def _setup_ffmpeg_bin():
    try:
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "assets" / "ffmpeg_bin")
        candidates.append(BASE_DIR / "assets" / "ffmpeg_bin")
        candidates.append(BASE_DIR / "_internal" / "assets" / "ffmpeg_bin")
        for ffmpeg_dir in candidates:
            if ffmpeg_dir.exists():
                f_str = str(ffmpeg_dir)
                curr_path = os.environ.get("PATH", "")
                if f_str not in curr_path.split(os.pathsep):
                    os.environ["PATH"] = f_str + os.pathsep + curr_path
                exe = ffmpeg_dir / "ffmpeg.exe"
                if exe.exists():
                    os.environ["FFMPEG_BINARY"] = str(exe)
                break
    except Exception:
        pass


_setup_ffmpeg_bin()

