"""Self-check and smoke test for Neu Audio Studio.

Runs an assert-based self-check without external test frameworks.
"""
import sys
import os
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure offscreen Qt platform for headless CI / command-line execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from core.config import (
    BASE_DIR,
    MODELS_DIR,
    ASSETS_DIR,
    OUTPUTS_DIR,
    EXAMPLES_DIR,
    DEFAULT_VOICE,
    APP_NAME,
)
from core.model_manager import ModelManager
from engines.tts_engine import TTSEngine
from engines.stt_engine import STTEngine
from ui.styles import GLOBAL_STYLESHEET, BG_MAIN, BG_SURFACE, ACCENT_PRIMARY
from ui.main_window import MainWindow


def test_core_and_config():
    print("[1/5] Testing core configuration and directories...")
    assert BASE_DIR.exists(), "BASE_DIR does not exist"
    assert MODELS_DIR.exists(), "MODELS_DIR does not exist"
    assert ASSETS_DIR.exists(), "ASSETS_DIR does not exist"
    assert OUTPUTS_DIR.exists(), "OUTPUTS_DIR does not exist"
    assert EXAMPLES_DIR.exists(), "EXAMPLES_DIR does not exist"
    assert (EXAMPLES_DIR / "sample_ref.wav").exists(), "sample_ref.wav should exist in examples"
    assert DEFAULT_VOICE == "Trúc Ly"

    mm = ModelManager()
    assert mm.models_dir == MODELS_DIR
    assert mm.vieneu_dir.exists()
    print("  -> Passed.")


def test_engines():
    print("[2/5] Testing AI engines...")
    tts = TTSEngine()
    voices = tts.list_preset_voices()
    assert len(voices) >= 10, f"Expected at least 10 VieNeu voices, got {len(voices)}"

    # Multi-model switching check: VieNeu and OmniVoice
    tts.set_model_type("omnivoice")
    assert len(tts.list_preset_voices()) == 0, "OmniVoice should have no preset voices (voice clone only)"
    assert tts.supports_voice_clone
    tts.set_model_type("vieneu")
    assert tts.supports_voice_clone
    voice_ids = [v["id"] for v in voices]
    assert "Trúc Ly" in voice_ids, "Trúc Ly should be in preset voices"
    assert "Phạm Tuyên" in voice_ids, "Phạm Tuyên should be in preset voices"
    pham_tuyen = next(v for v in voices if v["id"] == "Phạm Tuyên")
    assert pham_tuyen["label"] == "Phạm Tuyên - Nam - Miền Bắc", f"Expected 'Phạm Tuyên - Nam - Miền Bắc', got {pham_tuyen['label']}"

    stt = STTEngine()
    assert stt.compute_type in ["int8", "float16"], f"Unexpected compute type: {stt.compute_type}"

    from engines.stt_engine import format_srt
    mock_segments = [{"start": 0.0, "end": 2.5, "text": "Xin chào"}, {"start": 2.5, "end": 5.0, "text": "Việt Nam"}]
    srt_out = format_srt(mock_segments)
    assert "00:00:00,000 --> 00:00:02,500" in srt_out, "SRT formatting must produce valid timestamp markers"

    if stt.is_model_downloaded():
        res = stt.transcribe(EXAMPLES_DIR / "sample_ref.wav", beam_size=1)
        assert len(res["text"]) > 0, "Transcribe should return recognized text"
        assert res["language"] == "vi", "Language should be detected/set as Vietnamese"

    print("  -> Passed.")


def test_styles():
    print("[3/5] Testing design tokens and stylesheet...")
    assert BG_MAIN == "#F8FAFC"
    assert BG_SURFACE == "#FFFFFF"
    assert ACCENT_PRIMARY == "#4F46E5"
    assert "#F8FAFC" in GLOBAL_STYLESHEET
    assert "#FFFFFF" in GLOBAL_STYLESHEET
    assert "#4F46E5" in GLOBAL_STYLESHEET
    assert "sidebarFrame" in GLOBAL_STYLESHEET
    print("  -> Passed.")


def test_ui_components_offscreen():
    print("[4/5] Testing PyQt6 GUI hierarchy and view routing...")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLESHEET)

    window = MainWindow()
    assert window.windowTitle().startswith(APP_NAME)
    assert window.stack.count() == 3, "Expected 3 views in stack router (TTS, STT, Settings)"

    # Test view switching: STT
    window._switch_view(1)
    assert window.stack.currentIndex() == 1
    assert window.btn_nav_stt.property("active") == "true"
    assert window.btn_nav_tts.property("active") == "false"
    assert window.stt_view.transcript_box.isReadOnly(), "STT transcript box must be read-only"
    assert window.stt_view.btn_select_file.isEnabled()
    assert window.stt_view.btn_transcribe.isEnabled()

    # Test view switching: Settings
    window._switch_view(2)
    assert window.stack.currentIndex() == 2
    assert window.btn_nav_settings.property("active") == "true"

    # Test view switching: TTS
    window._switch_view(0)
    assert window.stack.currentIndex() == 0
    assert window.btn_nav_tts.property("active") == "true"
    assert window.btn_nav_stt.property("active") == "false"

    # Test model switching and states in TTS View
    window._on_model_changed("omnivoice")
    window._switch_view(0)
    assert window.tts_view.btn_synthesize.text() == "Tạo giọng nói"
    # OmniVoice has no default preset voices, only Voice Clone
    assert len(window.tts_view._preset_pills) == 0
    assert not window.tts_view.clone_pill.isHidden()
    assert window.tts_view.clone_pill.isChecked()

    # Verify Settings has exactly 2 models (OmniVoice & VieNeu)
    from ui.views.settings_view import _MODEL_INFO
    assert len(_MODEL_INFO) == 2, f"Expected 2 models in settings, got {len(_MODEL_INFO)}"
    model_keys = [m["key"] for m in _MODEL_INFO]
    assert "omnivoice" in model_keys and "vieneu" in model_keys
    assert "kokoro" not in model_keys

    # Switch back to VieNeu
    window._on_model_changed("vieneu")
    window._switch_view(0)
    if window.tts_view.engine.model_manager.is_vieneu_downloaded():
        assert window.tts_view.btn_synthesize.text() == "Tạo giọng nói"
        assert not window.tts_view.pills_widget.isHidden()
        assert len(window.tts_view._preset_pills) >= 10
        assert not window.tts_view.clone_pill.isHidden()
    else:
        # Not downloaded: button must be 'Tải Model' and pills must be hidden
        assert window.tts_view.btn_synthesize.text() == "Tải Model"
        assert window.tts_view.pills_widget.isHidden()

    # Verify speed slider UI
    assert hasattr(window.tts_view, "speed_slider"), "TTSView must have speed_slider"
    assert window.tts_view.speed_slider.value() == 100, "Default speed slider value should be 100 (1.0x)"
    window.tts_view.speed_slider.setValue(150)
    assert window.tts_view.speed_val_badge.text() == "1.5x"
    window.tts_view.btn_reset_speed.click()
    assert window.tts_view.speed_slider.value() == 100
    assert window.tts_view.speed_val_badge.text() == "1.0x"

    # Test player component
    sample_file = EXAMPLES_DIR / "sample_ref.wav"
    window.tts_view.player_card.load_audio(sample_file, description="Test sample")
    assert window.tts_view.player_card.play_btn.isEnabled()
    assert window.tts_view.player_card.export_btn.isEnabled()

    print("  -> Passed.")


def test_voice_cloning_reference():
    print("[5/5] Testing reference audio file parameter validation...")
    tts = TTSEngine()
    sample_file = EXAMPLES_DIR / "sample_ref.wav"
    assert sample_file.exists()

    # Input validation guard check
    try:
        tts.synthesize(text="   ")
        assert False, "Should raise ValueError on empty text"
    except ValueError:
        pass

    print("  -> Passed.")


if __name__ == "__main__":
    print("=== Running Neu Audio Studio Self-Check ===")
    test_core_and_config()
    test_engines()
    test_styles()
    test_ui_components_offscreen()
    test_voice_cloning_reference()
    print("=== All 5 checks PASSED successfully! ===")
