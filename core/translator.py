"""Translation utility for Speech-to-Text and subtitle processing.

Provides lightweight text and segment translation using standard library HTTP client.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_TRANSLATION_LANGUAGES: List[Tuple[str, str]] = [
    ("Tiếng Việt", "vi"),
    ("Tiếng Anh", "en"),
    ("Tiếng Trung", "zh-CN"),
    ("Tiếng Nhật", "ja"),
    ("Tiếng Hàn", "ko"),
    ("Tiếng Pháp", "fr"),
    ("Tiếng Đức", "de"),
    ("Tiếng Tây Ban Nha", "es"),
    ("Tiếng Nga", "ru"),
]


def translate_text(text: str, target_lang: str = "vi", source_lang: str = "auto") -> str:
    """Translate plain text into the target language."""
    if not text or not text.strip():
        return ""

    # Split large text into chunks if exceeding ~2000 characters to prevent URL length limits
    if len(text) > 2000:
        paragraphs = text.split("\n")
        translated_paragraphs: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for p in paragraphs:
            if current_len + len(p) > 2000 and current_chunk:
                translated_paragraphs.append(_translate_single_chunk("\n".join(current_chunk), target_lang, source_lang))
                current_chunk = [p]
                current_len = len(p)
            else:
                current_chunk.append(p)
                current_len += len(p) + 1

        if current_chunk:
            translated_paragraphs.append(_translate_single_chunk("\n".join(current_chunk), target_lang, source_lang))

        return "\n".join(translated_paragraphs)

    return _translate_single_chunk(text, target_lang, source_lang)


def _translate_single_chunk(chunk: str, target_lang: str, source_lang: str) -> str:
    """Send a single chunk of text to the translation endpoint."""
    if not chunk.strip():
        return ""
    try:
        url = (
            f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q="
            + urllib.parse.quote(chunk)
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                return "".join([part[0] for part in data[0] if part and part[0]])
            return chunk
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        return chunk


def translate_segments(
    segments: List[Dict[str, Any]],
    target_lang: str = "vi",
    source_lang: str = "auto",
) -> List[Dict[str, Any]]:
    """Translate speech segments with preserved start and end timestamps."""
    if not segments:
        return []

    translated_segments: List[Dict[str, Any]] = []
    delimiter = " ||| "
    batch_size = 20

    for i in range(0, len(segments), batch_size):
        batch = segments[i : i + batch_size]
        texts = [s.get("text", "").strip() for s in batch]
        joined = delimiter.join(texts)

        try:
            translated_joined = _translate_single_chunk(joined, target_lang, source_lang)
            parts = [p.strip() for p in translated_joined.split("|||")]

            if len(parts) == len(batch):
                for s, tr_text in zip(batch, parts):
                    translated_segments.append({
                        "start": s.get("start", 0.0),
                        "end": s.get("end", 0.0),
                        "text": tr_text,
                    })
            else:
                # Fallback: translate individually if delimiter count mismatched
                for s in batch:
                    orig = s.get("text", "").strip()
                    tr = _translate_single_chunk(orig, target_lang, source_lang) if orig else ""
                    translated_segments.append({
                        "start": s.get("start", 0.0),
                        "end": s.get("end", 0.0),
                        "text": tr,
                    })
        except Exception:
            for s in batch:
                translated_segments.append({
                    "start": s.get("start", 0.0),
                    "end": s.get("end", 0.0),
                    "text": s.get("text", ""),
                })

    return translated_segments
