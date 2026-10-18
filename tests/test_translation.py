import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.translator import translate_text, translate_segments

def test_translation():
    text = "Tóm tắt bộ kỹ năng của Rengar nội tại mùi vị thách thức, dây chuyền răng nanh.\nKhi đứng trong bụi cỏ, Rengar có thể nhảy vào mục tiêu bằng đòn đánh thường."
    translated = translate_text(text, target_lang="en")
    assert len(translated) > 0, "Translated text should not be empty"
    assert "Tóm tắt" not in translated, f"Text should be translated to English, got: {translated}"
    assert "Rengar" in translated

    # Test segment translation
    segs = [
        {"start": 0.0, "end": 2.0, "text": "Xin chào"},
        {"start": 2.0, "end": 4.0, "text": "Tạm biệt"}
    ]
    tr_segs = translate_segments(segs, target_lang="en")
    assert len(tr_segs) == 2
    assert "Xin chào" not in tr_segs[0]["text"]
    assert tr_segs[0]["start"] == 0.0

    print("All translation tests passed successfully!")

if __name__ == "__main__":
    test_translation()
