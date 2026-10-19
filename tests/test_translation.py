import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.translator import (
    translate_text,
    translate_segments,
    get_ctranslate2_translator,
    is_ctranslate2_available,
    is_ctranslate2_loaded,
)

def test_translation():
    # Test CTranslate2 Translator setup & language mapping
    ct2 = get_ctranslate2_translator()
    assert ct2 is not None
    assert ct2.map_to_nllb_code("vi") == "vie_Latn"
    assert ct2.map_to_nllb_code("en") == "eng_Latn"
    assert ct2.map_to_nllb_code("zh-CN") == "zho_Hans"
    assert ct2.map_to_nllb_code("ja") == "jpn_Jpan"
    assert ct2.detect_nllb_lang("Xin chào bạn") == "vie_Latn"
    assert ct2.detect_nllb_lang("Hello world") == "eng_Latn"

    text = "Tóm tắt bộ kỹ năng của Rengar nội tại mùi vị thách thức, dây chuyền răng nanh.\nKhi đứng trong bụi cỏ, Rengar có thể nhảy vào mục tiêu bằng đòn đánh thường."
    translated = translate_text(text, target_lang="en")
    assert len(translated) > 0, "Translated text should not be empty"
    assert "Tóm tắt" not in translated, f"Text should be translated to English, got: {translated}"
    assert "Rengar" in translated

    # Test segment translation with special characters (#, [], &, emojis)
    segs = [
        {"start": 0.0, "end": 2.0, "text": "Hôm nay chúng ta học lập trình C#."},
        {"start": 2.0, "end": 4.0, "text": "Khán giả phản ứng [vỗ tay] nồng nhiệt."},
        {"start": 4.0, "end": 6.0, "text": "Đừng quên like & share nhé #1 #review!"},
    ]
    tr_segs = translate_segments(segs, target_lang="en")
    assert len(tr_segs) == 3
    assert tr_segs[0]["start"] == 0.0
    assert tr_segs[1]["start"] == 2.0
    assert tr_segs[2]["start"] == 4.0
    # Ensure # and [] content is preserved in translation
    assert "C#" in tr_segs[0]["text"]
    assert any(w in tr_segs[1]["text"].lower() for w in ["audience", "applause", "clap", "warmly", "vỗ tay", "response"])
    assert "#" in tr_segs[2]["text"]

    # Test multi-paragraph text preserving empty lines
    multi_para = "Đoạn văn thứ nhất.\n\nĐoạn văn thứ hai sau dòng trống."
    tr_para = translate_text(multi_para, target_lang="en")
    assert "\n\n" in tr_para or "\n" in tr_para
    assert len(tr_para.split("\n")) >= 2

    # Test same language shortcut (identity, no network call)
    same_lang = translate_text("Văn bản tiếng Việt", target_lang="vi", source_lang="vi")
    assert same_lang == "Văn bản tiếng Việt"

    # Test long text without newlines (exceeding single chunk limit ~5000 chars)
    long_text = "Đây là một câu hoàn chỉnh dùng để kiểm tra tính năng chia nhỏ đoạn văn bản khi dịch. " * 80
    assert len(long_text) > 4000
    long_translated = translate_text(long_text, target_lang="en")
    assert len(long_translated) > 0
    assert "This is a" in long_translated or "complete sentence" in long_translated

    print("All translation tests passed successfully!")

if __name__ == "__main__":
    test_translation()

