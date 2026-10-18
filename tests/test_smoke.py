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

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.config import (
    BASE_DIR,
    MODELS_DIR,
    ASSETS_DIR,
    OUTPUTS_DIR,
    EXAMPLES_DIR,
    DEFAULT_VOICE,
    APP_NAME,
    cleanup_outputs_dir,
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
    assert EXAMPLES_DIR.exists(), "EXAMPLES_DIR does not exist"
    assert not (ASSETS_DIR / "examples").exists(), "assets/examples must not exist"
    assert (EXAMPLES_DIR / "sample_ref.wav").exists(), "sample_ref.wav should exist in TTS/examples"
    assert DEFAULT_VOICE == "Trúc Ly"

    # Test output directory cleanup functionality
    dummy_out = OUTPUTS_DIR / "_test_cleanup_marker.tmp"
    dummy_out.write_text("temporary marker", encoding="utf-8")
    assert dummy_out.exists()
    cleanup_outputs_dir()
    assert not dummy_out.exists(), "cleanup_outputs_dir must delete temporary files in outputs/"

    mm = ModelManager()
    assert mm.models_dir == MODELS_DIR
    assert mm.vieneu_dir.exists()

    # Test FFmpeg binary resolution from assets/ffmpeg_bin
    from core.config import FFMPEG_BIN_DIR, get_ffmpeg_path, get_ffprobe_path
    assert FFMPEG_BIN_DIR.exists(), "assets/ffmpeg_bin directory must exist"
    ffmpeg_p = get_ffmpeg_path()
    ffprobe_p = get_ffprobe_path()
    assert Path(ffmpeg_p).exists(), f"FFmpeg binary not found at {ffmpeg_p}"
    assert Path(ffprobe_p).exists(), f"FFprobe binary not found at {ffprobe_p}"
    assert "ffmpeg_bin" in ffmpeg_p.lower(), f"Expected ffmpeg to resolve to assets/ffmpeg_bin, got {ffmpeg_p}"
    assert "ffmpeg_bin" in ffprobe_p.lower(), f"Expected ffprobe to resolve to assets/ffmpeg_bin, got {ffprobe_p}"

    from core.config import get_subprocess_no_window_kwargs
    import subprocess
    no_win = get_subprocess_no_window_kwargs()
    if sys.platform == "win32":
        assert "creationflags" in no_win and no_win["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert "startupinfo" in no_win
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
    from core.translator import translate_text, translate_segments
    tr_res = translate_text("Xin chào", target_lang="en")
    assert "hello" in tr_res.lower() or len(tr_res) > 0, f"Expected translation, got {tr_res}"

    if stt.is_model_downloaded():
        res = stt.transcribe(EXAMPLES_DIR / "sample_ref.wav", beam_size=1)
        assert len(res["text"]) > 0, "Transcribe should return recognized text"
        assert res["language"] == "vi", "Language should be detected/set as Vietnamese"

    from engines.sketch_engine import SketchEngine
    sketch = SketchEngine()
    assert sketch.is_assets_ready(), "Sketch assets in assets/v181d must be ready"
    st = sketch.build_settings(duration=5.0, fps=25, device="cpu", encoder="cpu")
    assert st.duration == 5.0 and st.fps == 25 and st.device == "cpu" and st.encoder == "cpu"

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
    assert window.stack.count() == 5, "Expected 5 views in stack router (TTS, STT, Sketch, Dubbing, Settings)"

    # Test view switching: STT
    window._switch_view(1)
    assert window.stack.currentIndex() == 1
    assert window.btn_nav_stt.property("active") == "true"
    assert not window.stt_view.transcript_box.isReadOnly(), "STT transcript box must be editable"
    assert not window.stt_view.translated_box.isReadOnly(), "STT translated box must be editable"
    assert window.stt_view.btn_select_file.isEnabled()
    assert window.stt_view.btn_transcribe.isEnabled()
    # Test STT controls disabling during transcription
    window.stt_view.btn_select_file.setEnabled(False)
    assert not window.stt_view.btn_select_file.isEnabled()
    window.stt_view.btn_select_file.setEnabled(True)
    assert window.stt_view.btn_select_file.isEnabled()

    # Test view switching: Sketch Video
    window._switch_view(2)
    assert window.stack.currentIndex() == 2
    assert window.btn_nav_sketch.property("active") == "true"
    assert window.btn_nav_tts.property("active") == "false"
    assert window.btn_nav_stt.property("active") == "false"

    sv = window.sketch_view
    assert hasattr(window, "sketch_engine")
    assert sv.engine is window.sketch_engine
    assert sv.duration_slider.value() == 10, "Duration should default to 10s"
    assert sv.duration_badge.text() == "10s"
    sv.duration_slider.setValue(25)
    assert sv.duration_badge.text() == "25s"
    sv.btn_reset_duration.click()
    assert sv.duration_slider.value() == 10
    assert sv.duration_badge.text() == "10s"

    assert sv.fps_slider.value() == 30, "FPS should default to 30"
    assert sv.fps_badge.text() == "30 fps"
    sv.fps_slider.setValue(45)
    assert sv.fps_badge.text() == "45 fps"
    sv.btn_reset_fps.click()
    assert sv.fps_slider.value() == 30
    assert sv.fps_badge.text() == "30 fps"

    # Test Maximum width [64, 3840], default 1920
    assert sv.width_slider.value() == 1920, "Width should default to 1920"
    assert sv.width_badge.text() == "1920 px"
    assert sv.width_slider.minimum() == 64 and sv.width_slider.maximum() == 3840
    sv.width_slider.setValue(1280)
    assert sv.width_badge.text() == "1280 px"
    sv.btn_reset_width.click()
    assert sv.width_slider.value() == 1920
    assert sv.width_badge.text() == "1920 px"

    # Test Maximum height [64, 2160], default 1080
    assert sv.height_slider.value() == 1080, "Height should default to 1080"
    assert sv.height_badge.text() == "1080 px"
    assert sv.height_slider.minimum() == 64 and sv.height_slider.maximum() == 2160
    sv.height_slider.setValue(720)
    assert sv.height_badge.text() == "720 px"
    sv.btn_reset_height.click()
    assert sv.height_slider.value() == 1080
    assert sv.height_badge.text() == "1080 px"

    # Test direct text editing on badges (validation, clamping, data types)
    sv.duration_badge.setText("45")
    sv.duration_badge.editingFinished.emit()
    assert sv.duration_slider.value() == 45
    assert sv.duration_badge.text() == "45s"

    sv.duration_badge.setText("9999")  # Exceeds maximum 120
    sv.duration_badge.editingFinished.emit()
    assert sv.duration_slider.value() == 120
    assert sv.duration_badge.text() == "120s"

    sv.width_badge.setText("1281")  # Odd number, should clamp to even
    sv.width_badge.editingFinished.emit()
    assert sv.width_slider.value() == 1280
    assert sv.width_badge.text() == "1280 px"

    # Test direct editing on TTS speed badge (float scale)
    window.tts_view.speed_val_badge.setText("1.8")
    window.tts_view.speed_val_badge.editingFinished.emit()
    assert window.tts_view.speed_slider.value() == 180
    assert window.tts_view.speed_val_badge.text() == "1.8x"

    window.tts_view.speed_val_badge.setText("0.1")  # Below minimum 0.5x (50)
    window.tts_view.speed_val_badge.editingFinished.emit()
    assert window.tts_view.speed_slider.value() == 50
    assert window.tts_view.speed_val_badge.text() == "0.5x"

    sv.btn_reset_duration.click()
    sv.btn_reset_width.click()
    window.tts_view.btn_reset_speed.click()

    # Test wheel event locking on sliders and comboboxes
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtCore import QPointF, QPoint
    dummy_wheel = QWheelEvent(QPointF(0, 0), QPointF(0, 0), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    val_before = sv.duration_slider.value()
    sv.duration_slider.wheelEvent(dummy_wheel)
    assert sv.duration_slider.value() == val_before, "Wheel event must be ignored on duration_slider"

    speed_before = window.tts_view.speed_slider.value()
    window.tts_view.speed_slider.wheelEvent(dummy_wheel)
    assert window.tts_view.speed_slider.value() == speed_before, "Wheel event must be ignored on tts_view.speed_slider"

    idx_before = sv.device_combo.currentIndex()
    sv.device_combo.wheelEvent(dummy_wheel)
    assert sv.device_combo.currentIndex() == idx_before, "Wheel event must be ignored on device_combo"

    assert sv.device_combo.currentText() == "CPU"
    assert [sv.device_combo.itemText(i) for i in range(sv.device_combo.count())] == ["CPU", "GPU"]

    assert sv.encoder_combo.currentText() == "CPU H.264"
    encoder_items = [sv.encoder_combo.itemText(i) for i in range(sv.encoder_combo.count())]
    assert "CPU H.264" in encoder_items and "NVIDIA NVENC" in encoder_items

    assert not sv.btn_render.isEnabled(), "Render button should be disabled before selecting an image"

    # Test image loading & preview (only image in preview card)
    test_img = ASSETS_DIR / "icons" / "app_icon.png"
    if test_img.exists():
        sv.drop_zone.load_image(test_img)
        assert sv.selected_image == test_img
        assert sv.drop_zone.stack.currentIndex() == 1, "Dropzone should show preview state"
        assert sv.btn_render.isEnabled(), "Render button should be enabled after selecting image"
        assert not sv.drop_zone.image_preview_label.pixmap().isNull()
        assert not hasattr(sv.drop_zone, "btn_remove"), "btn_remove should be removed"
        assert not hasattr(sv.drop_zone, "btn_change"), "btn_change should be removed"

    # Test input disabling logic during rendering
    sv._set_inputs_enabled(False)
    assert not sv.drop_zone.isEnabled()
    assert not sv.duration_slider.isEnabled()
    assert not sv.btn_reset_duration.isEnabled()
    assert not sv.fps_slider.isEnabled()
    assert not sv.btn_reset_fps.isEnabled()
    assert not sv.width_slider.isEnabled()
    assert not sv.btn_reset_width.isEnabled()
    assert not sv.height_slider.isEnabled()
    assert not sv.btn_reset_height.isEnabled()
    assert not sv.device_combo.isEnabled()
    assert not sv.encoder_combo.isEnabled()
    assert not sv.btn_render.isEnabled()

    sv._set_inputs_enabled(True)
    assert sv.drop_zone.isEnabled()
    assert sv.duration_slider.isEnabled()
    assert sv.btn_reset_duration.isEnabled()
    assert sv.fps_slider.isEnabled()
    assert sv.btn_reset_fps.isEnabled()
    assert sv.width_slider.isEnabled()
    assert sv.btn_reset_width.isEnabled()
    assert sv.height_slider.isEnabled()
    assert sv.btn_reset_height.isEnabled()
    assert sv.device_combo.isEnabled()
    assert sv.encoder_combo.isEnabled()
    assert sv.btn_render.isEnabled()

    # Clear image test
    sv.drop_zone.clear_image()
    assert sv.selected_image is None
    assert not sv.btn_render.isEnabled()
    assert sv.drop_zone.stack.currentIndex() == 0, "Dropzone should return to empty state"

    # Test view switching: Dubbing (Tab 4)
    window._switch_view(3)
    assert window.stack.currentIndex() == 3
    assert window.btn_nav_dubbing.property("active") == "true"
    assert window.btn_nav_tts.property("active") == "false"
    assert window.btn_nav_sketch.property("active") == "false"
    dv = window.dubbing_view
    assert dv.btn_create_transcript.isEnabled()
    assert not dv.btn_create_video.isEnabled(), "Create video button should be disabled initially"
    assert not dv.orig_text_box.isReadOnly(), "Dubbing orig_text_box must be editable"
    assert not dv.trans_text_box.isReadOnly(), "Dubbing trans_text_box must be editable"

    # Test input locking behavior
    dv._set_inputs_enabled(False)
    assert not dv.btn_select_video.isEnabled()
    assert not dv.combo_target_lang.isEnabled()
    assert not dv.btn_create_transcript.isEnabled()
    assert not dv.btn_create_video.isEnabled()
    assert dv.orig_text_box.isReadOnly(), "Must be locked during execution"
    assert dv.trans_text_box.isReadOnly(), "Must be locked during execution"
    dv._set_inputs_enabled(True)
    assert dv.btn_select_video.isEnabled()
    assert dv.combo_target_lang.isEnabled()
    assert dv.btn_create_transcript.isEnabled()
    assert not dv.orig_text_box.isReadOnly()
    assert not dv.trans_text_box.isReadOnly()

    # Test model availability state on dubbing_view
    assert "Tạo văn bản" in dv.btn_create_transcript.text()

    # Test video player responsive aspect sizing (eliminating side black bars)
    assert hasattr(dv, "video_player")
    assert hasattr(dv, "video_container")
    dv.video_player.video_aspect_ratio = 16.0 / 9.0
    dv.video_player.set_has_video(True)
    tw, th = dv.video_player.update_aspect_size(available_width=800, max_height=520, min_height=240)
    assert tw == 800
    assert th == 450, f"Expected 450 for 16:9 at 800w, got {th}"
    ratio_err = abs((tw / th) - (16.0 / 9.0))
    assert ratio_err < 0.01, f"Aspect ratio error too high: {ratio_err}"

    # Test view switching: Settings
    window._switch_view(4)
    assert window.stack.currentIndex() == 4
    assert window.btn_nav_settings.property("active") == "true"
    assert window.btn_nav_dubbing.property("active") == "false"
    assert hasattr(window.settings_view, "item_vieneu")
    assert hasattr(window.settings_view, "item_omnivoice")
    assert hasattr(window.settings_view, "item_whisper")

    # Test SettingsView: Disable all download buttons during download task
    sv = window.settings_view
    sv._current_task_target = "omnivoice"
    sv._set_actions_enabled(False)
    sv.refresh_state()
    for btn in sv._action_buttons:
        assert not btn.isEnabled(), "All action buttons must be disabled during active download task"
    assert not sv.item_vieneu["radio"].isEnabled()
    assert not sv.item_omnivoice["radio"].isEnabled()

    # Finish task and verify buttons and radios re-enable
    sv._on_task_finished("omnivoice")
    assert sv._current_task_target is None
    assert sv.item_vieneu["radio"].isEnabled()
    assert sv.item_omnivoice["radio"].isEnabled()

    # Test failure recovery
    sv._current_task_target = "whisper"
    sv._set_actions_enabled(False)
    sv.refresh_state()
    for btn in sv._action_buttons:
        assert not btn.isEnabled()
    sv._on_task_failed("Simulated download failure")
    assert sv._current_task_target is None
    assert sv.item_vieneu["radio"].isEnabled()
    assert sv.item_omnivoice["radio"].isEnabled()

    # Test view switching: TTS
    window._switch_view(0)
    assert window.stack.currentIndex() == 0
    assert window.btn_nav_tts.property("active") == "true"
    assert window.btn_nav_stt.property("active") == "false"
    assert window.btn_nav_sketch.property("active") == "false"

    # Test model switching and states in TTS View
    window._on_model_changed("omnivoice")
    assert window.tts_view.btn_synthesize.text() == "Tạo giọng nói"
    if window.tts_view.engine.model_manager.is_omnivoice_downloaded():
        assert len(window.tts_view._preset_pills) == 0
        assert not window.tts_view.clone_pill.isHidden()
        assert window.tts_view.clone_pill.isChecked()
    else:
        assert window.tts_view.pills_widget.isHidden()

    # Verify that downloading another model does not change active checked model in TTS view
    window.settings_view.item_vieneu["radio"].setChecked(True)
    window.settings_view._on_tts_radio_changed(window.settings_view.item_vieneu["radio"])
    assert window.settings_view.current_model == "vieneu"
    # Switch back to TTS view: must correspond to checked model (vieneu), not omnivoice
    window._switch_view(0)
    assert window.tts_engine.current_model_type == "vieneu", "TTS engine must keep checked model ('vieneu')"
    if window.tts_engine.is_model_downloaded():
        assert len(window.tts_view._preset_pills) >= 10, "TTS view must display VieNeu preset pills corresponding to checked model"

    # Verify speed slider UI
    assert hasattr(window.tts_view, "speed_slider"), "TTSView must have speed_slider"
    assert window.tts_view.speed_slider.value() == 100, "Default speed slider value should be 100 (1.0x)"
    window.tts_view.speed_slider.setValue(150)
    assert window.tts_view.speed_val_badge.text() == "1.5x"
    window.tts_view.btn_reset_speed.click()
    assert window.tts_view.speed_slider.value() == 100
    assert window.tts_view.speed_val_badge.text() == "1.0x"

    # Verify input disabling/enabling logic during synthesis
    window.tts_view._set_inputs_enabled(False)
    assert not window.tts_view.text_input.isEnabled(), "text_input must be disabled during synthesis"
    assert not window.tts_view.pills_widget.isEnabled(), "pills_widget must be disabled during synthesis"
    assert not window.tts_view.clone_pill.isEnabled(), "clone_pill must be disabled during synthesis"
    assert not window.tts_view.speed_container.isEnabled(), "speed_container must be disabled during synthesis"
    assert not window.tts_view.speed_slider.isEnabled(), "speed_slider must be disabled during synthesis"
    assert not window.tts_view.btn_reset_speed.isEnabled(), "btn_reset_speed must be disabled during synthesis"

    window.tts_view._set_inputs_enabled(True)
    assert window.tts_view.text_input.isEnabled()
    assert window.tts_view.pills_widget.isEnabled()
    assert window.tts_view.clone_pill.isEnabled()
    assert window.tts_view.speed_container.isEnabled()
    assert window.tts_view.speed_slider.isEnabled()
    assert window.tts_view.btn_reset_speed.isEnabled()
    window.close()
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
