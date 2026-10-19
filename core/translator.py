"""Translation utility for Speech-to-Text, subtitles, and video dubbing.

Supports offline local inference via CTranslate2 (NLLB-200 Distilled INT8)
with automatic fallback to multi-provider web services (Google Mobile, Bing, Google Web, MyMemory)
when the local model has not been downloaded yet.
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from core.config import NLLB_DIR

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

# NLLB-200 Language Code mapping
NLLB_LANG_CODES: Dict[str, str] = {
    "vi": "vie_Latn",
    "en": "eng_Latn",
    "zh": "zho_Hans",
    "zh-cn": "zho_Hans",
    "zh-hans": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "es": "spa_Latn",
    "ru": "rus_Cyrl",
}

# Cooldown timestamps for web endpoints in case of rate limiting
_google_web_cooldown_until: float = 0.0
_bing_cooldown_until: float = 0.0


# ─── CTranslate2 Local Offline Translation Engine ─────────────────────────────

class CTranslate2Translator:
    """Thread-safe CTranslate2 translation engine using Meta's NLLB-200 INT8 model."""

    _instance: Optional["CTranslate2Translator"] = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self.model_dir = NLLB_DIR
        self._translator = None
        self._tokenizer = None
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "CTranslate2Translator":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_downloaded(self) -> bool:
        """Check if local CTranslate2 NLLB weights and tokenizer exist on disk."""
        return (
            (self.model_dir / "model.bin").is_file()
            and (self.model_dir / "shared_vocabulary.txt").is_file()
            and (self.model_dir / "tokenizer.json").is_file()
        )

    def is_loaded(self) -> bool:
        """Check if model and tokenizer are loaded in memory."""
        return self._translator is not None and self._tokenizer is not None

    def load(self) -> bool:
        """Load CTranslate2 translator and Hugging Face fast tokenizer."""
        if not self.is_downloaded():
            return False

        with self._lock:
            if self._translator is not None and self._tokenizer is not None:
                return True

            try:
                import ctranslate2
                from transformers import AutoTokenizer

                device = "cpu"
                try:
                    if ctranslate2.get_cuda_device_count() > 0:
                        device = "cuda"
                except Exception:
                    device = "cpu"

                logger.info(f"Loading CTranslate2 NLLB model from {self.model_dir} on device={device}...")
                self._translator = ctranslate2.Translator(
                    str(self.model_dir),
                    device=device,
                    compute_type="int8",
                    inter_threads=1,
                    intra_threads=4,
                )
                self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
                logger.info("CTranslate2 NLLB model loaded successfully.")
                return True
            except Exception as e:
                logger.error(f"Failed to load CTranslate2 translator: {e}", exc_info=True)
                self._translator = None
                self._tokenizer = None
                return False

    @staticmethod
    def detect_nllb_lang(text: str) -> str:
        """Fast heuristic detection of source language code when source is 'auto'."""
        if re.search(r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]', text, re.IGNORECASE):
            return "vie_Latn"
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
            return "jpn_Jpan"
        if re.search(r'[\uac00-\ud7af]', text):
            return "kor_Hang"
        if re.search(r'[\u4e00-\u9fff]', text):
            return "zho_Hans"
        if re.search(r'[\u0400-\u04ff]', text):
            return "rus_Cyrl"
        return "eng_Latn"

    def map_to_nllb_code(self, lang_code: str, sample_text: str = "") -> str:
        """Map standard 2-letter language code to NLLB-200 BCP-47 style code."""
        if not lang_code or lang_code.lower() == "auto":
            return self.detect_nllb_lang(sample_text)
        cleaned = lang_code.lower().strip()
        if cleaned in NLLB_LANG_CODES:
            return NLLB_LANG_CODES[cleaned]
        prefix = cleaned.split("-")[0]
        if prefix in NLLB_LANG_CODES:
            return NLLB_LANG_CODES[prefix]
        return "eng_Latn"

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: str = "auto",
        beam_size: int = 2,
    ) -> List[str]:
        """Translate a batch of text strings with exact 1-to-1 correspondence."""
        if not texts:
            return []

        if not self.is_loaded() and not self.load():
            raise RuntimeError("Mô hình CTranslate2 chưa được nạp.")

        with self._lock:
            tgt_nllb = self.map_to_nllb_code(target_lang)
            results: List[str] = []

            # Group non-empty texts for efficient translation
            indices_to_translate = []
            tokens_to_translate = []

            for idx, text in enumerate(texts):
                stripped = text.strip()
                if not stripped:
                    results.append("")
                    continue

                src_nllb = self.map_to_nllb_code(source_lang, sample_text=stripped)
                if src_nllb == tgt_nllb:
                    results.append(stripped)
                    continue

                self._tokenizer.src_lang = src_nllb
                token_ids = self._tokenizer.encode(stripped)
                tokens = self._tokenizer.convert_ids_to_tokens(token_ids)

                indices_to_translate.append(idx)
                tokens_to_translate.append(tokens)
                results.append("")  # Placeholder to fill

            if not tokens_to_translate:
                return results

            # Batch translation via CTranslate2
            target_prefixes = [[tgt_nllb] for _ in tokens_to_translate]
            outputs = self._translator.translate_batch(
                tokens_to_translate,
                target_prefix=target_prefixes,
                beam_size=beam_size,
                max_decoding_length=512,
            )

            for orig_idx, out in zip(indices_to_translate, outputs):
                hyp = out.hypotheses[0]
                target_ids = self._tokenizer.convert_tokens_to_ids(hyp)
                decoded = self._tokenizer.decode(target_ids, skip_special_tokens=True).strip()
                results[orig_idx] = html.unescape(decoded)

            return results


def get_ctranslate2_translator() -> CTranslate2Translator:
    """Get the global CTranslate2Translator singleton."""
    return CTranslate2Translator.get_instance()


def is_ctranslate2_available() -> bool:
    """Check if local CTranslate2 NLLB model is downloaded and ready on disk."""
    return get_ctranslate2_translator().is_downloaded()


def is_ctranslate2_loaded() -> bool:
    """Check if local CTranslate2 NLLB model is currently loaded in memory."""
    return get_ctranslate2_translator().is_loaded()


# ─── Online Fallback Providers (Google Mobile, Bing, Google Web, MyMemory) ────

def _split_long_string(s: str, max_chars: int) -> List[str]:
    """Split a string at word boundaries to never cut words or multi-byte Unicode characters in half."""
    if len(s) <= max_chars:
        return [s]
    words = s.split(" ")
    parts: List[str] = []
    curr: List[str] = []
    curr_len = 0
    for w in words:
        if curr_len + len(w) + 1 > max_chars and curr:
            parts.append(" ".join(curr))
            curr = [w]
            curr_len = len(w)
        else:
            curr.append(w)
            curr_len += len(w) + 1
    if curr:
        parts.append(" ".join(curr))
    return parts if parts else [s]


def _translate_google_mobile(chunk: str, target_lang: str, source_lang: str) -> Optional[str]:
    """Translate text using Google Translate Android App client (client=at / client=it)."""
    s_lang = "auto" if source_lang in ["auto", ""] else source_lang
    t_lang = target_lang

    for client in ["at", "it"]:
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client={client}&sl={s_lang}&tl={t_lang}&dt=t"
            data = urllib.parse.urlencode({"q": chunk}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "User-Agent": "GoogleTranslate/6.29.0.04.436154162 (Linux; U; Android 12; Pixel 6)",
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data_json = json.loads(resp.read().decode("utf-8"))
                if data_json and isinstance(data_json, list) and len(data_json) > 0 and isinstance(data_json[0], list):
                    res = "".join(part[0] for part in data_json[0] if part and part[0])
                    if res:
                        return html.unescape(res)
        except Exception as e:
            logger.debug(f"Google mobile ({client}) failed: {e}")
    return None


def _translate_bing(chunk: str, target_lang: str, source_lang: str) -> Optional[str]:
    """Translate text using Bing Translator web API with a fresh session cookie."""
    global _bing_cooldown_until
    if time.time() < _bing_cooldown_until:
        return None

    if len(chunk) > 950:
        return None

    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        req = urllib.request.Request(
            "https://www.bing.com/translator",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        html_content = opener.open(req, timeout=8).read().decode("utf-8")
        ig_m = re.search(r'IG:"([^"]+)"', html_content)
        params_m = re.search(r'params_AbusePreventionHelper\s*=\s*\[([^\]]+)\]', html_content)
        if not ig_m or not params_m:
            return None

        ig = ig_m.group(1)
        iid_m = re.search(r'data-iid="([^"]+)"', html_content)
        iid = iid_m.group(1) if iid_m else "translator.5028"
        key, token, _ = [p.strip().strip('"') for p in params_m.group(1).split(",")]

        b_target = "zh-Hans" if target_lang.lower() in ["zh-cn", "zh"] else target_lang
        b_source = "auto-detect" if source_lang in ["auto", ""] else source_lang
        url = f"https://www.bing.com/ttranslatev3?isVertical=1&IG={ig}&IID={iid}"
        data = urllib.parse.urlencode({
            "fromLang": b_source,
            "to": b_target,
            "text": chunk,
            "key": key,
            "token": token,
        }).encode("utf-8")
        req2 = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        res = json.loads(opener.open(req2, timeout=10).read().decode("utf-8"))
        if res and isinstance(res, list) and len(res) > 0:
            translations = res[0].get("translations", [])
            if translations:
                return html.unescape(translations[0].get("text", ""))
    except Exception as e:
        logger.debug(f"Bing translate attempt failed: {e}")
        if "429" in str(e):
            _bing_cooldown_until = time.time() + 180.0
    return None


def _translate_google_web(chunk: str, target_lang: str, source_lang: str) -> Optional[str]:
    """Fallback using Google Translate Web client (dict-chrome-ex / gtx)."""
    global _google_web_cooldown_until
    if time.time() < _google_web_cooldown_until:
        return None

    s_lang = "auto" if source_lang in ["auto", ""] else source_lang
    t_lang = target_lang

    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl={s_lang}&tl={t_lang}&dt=t"
        data = urllib.parse.urlencode({"q": chunk}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data_json = json.loads(resp.read().decode("utf-8"))
            if data_json and isinstance(data_json, list) and len(data_json) > 0 and isinstance(data_json[0], list):
                res = "".join(part[0] for part in data_json[0] if part and part[0])
                if res:
                    return html.unescape(res)
    except Exception as e:
        if "429" in str(e):
            _google_web_cooldown_until = time.time() + 300.0
        logger.debug(f"Google web translate failed: {e}")
    return None


def _call_mymemory_api(chunk: str, s_lang: str, t_lang: str) -> Optional[str]:
    """Call MyMemory API for a short piece of text (<= 450 chars)."""
    try:
        url = "https://api.mymemory.translated.net/get"
        data = urllib.parse.urlencode({"q": chunk, "langpair": f"{s_lang}|{t_lang}"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data_json = json.loads(resp.read().decode("utf-8"))
            res = data_json.get("responseData", {}).get("translatedText")
            if res and not str(res).startswith("MYMEMORY WARNING"):
                return html.unescape(str(res))
    except Exception:
        pass
    return None


def _translate_mymemory(chunk: str, target_lang: str, source_lang: str) -> Optional[str]:
    """Fallback translation using MyMemory API with automatic sub-chunking."""
    try:
        s_lang = source_lang if source_lang != "auto" else "autodetect"
        t_lang = target_lang.split("-")[0] if "-" in target_lang and target_lang != "zh-CN" else target_lang

        if len(chunk) <= 450:
            return _call_mymemory_api(chunk, s_lang, t_lang)

        sub_chunks = _split_long_string(chunk, max_chars=400)
        translated_parts = []
        for sc in sub_chunks:
            if not sc.strip():
                continue
            res = _call_mymemory_api(sc, s_lang, t_lang)
            if not res:
                return None
            translated_parts.append(res)
        sep = "\n" if "\n" in chunk else " "
        return sep.join(translated_parts)
    except Exception as e:
        logger.debug(f"MyMemory translate fallback failed: {e}")
    return None


def _translate_single_chunk(chunk: str, target_lang: str, source_lang: str) -> str:
    """Send a single chunk of text to web translation endpoints with cascading multi-provider fallback."""
    if not chunk.strip():
        return ""

    # 1. Primary web: Google Mobile Android client (robust, fast, supports up to 4000+ chars)
    res = _translate_google_mobile(chunk, target_lang, source_lang)
    if res:
        return res

    # 2. Secondary web: Bing Translator (supports up to 950 chars, high quality)
    if len(chunk) <= 950:
        res = _translate_bing(chunk, target_lang, source_lang)
        if res:
            return res

    # 3. Tertiary web: Google Web client
    res = _translate_google_web(chunk, target_lang, source_lang)
    if res:
        return res

    # 4. Quaternary web: MyMemory API fallback (word-level chunking)
    res = _translate_mymemory(chunk, target_lang, source_lang)
    if res:
        return res

    raise RuntimeError("Không thể kết nối đến máy chủ dịch thuật. Vui lòng kiểm tra lại kết nối mạng.")


def _chunk_text(text: str, max_chars: int = 850) -> List[str]:
    """Split text into manageable chunks respecting paragraphs, sentences, and word boundaries."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n")
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for p in paragraphs:
        if not p.strip():
            if current_chunk:
                current_chunk.append("")
                current_len += 1
            else:
                chunks.append("")
            continue

        if len(p) <= max_chars:
            if current_len + len(p) + 1 > max_chars and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [p]
                current_len = len(p)
            else:
                current_chunk.append(p)
                current_len += len(p) + 1
        else:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            sentences = re.split(r"(?<=[.!?;\n])\s+", p)
            s_chunk: List[str] = []
            s_len = 0
            for s in sentences:
                if not s.strip():
                    continue
                if len(s) > max_chars:
                    if s_chunk:
                        chunks.append(" ".join(s_chunk))
                        s_chunk = []
                        s_len = 0
                    for part in _split_long_string(s, max_chars):
                        chunks.append(part)
                elif s_len + len(s) + 1 > max_chars and s_chunk:
                    chunks.append(" ".join(s_chunk))
                    s_chunk = [s]
                    s_len = len(s)
                else:
                    s_chunk.append(s)
                    s_len += len(s) + 1
            if s_chunk:
                chunks.append(" ".join(s_chunk))

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks if chunks else [text]


# ─── Public Translation Interfaces ───────────────────────────────────────────

def translate_text(text: str, target_lang: str = "vi", source_lang: str = "auto") -> str:
    """Translate plain text into the target language.

    Prioritizes local offline CTranslate2 model if downloaded; otherwise falls back to
    cascading online translation providers with automatic chunking.
    """
    if not text or not text.strip():
        return ""

    if source_lang != "auto" and source_lang.lower().startswith(target_lang.lower()[:2]):
        return text

    ct2 = get_ctranslate2_translator()
    if ct2.is_downloaded():
        try:
            # Paragraph-aware translation via local CTranslate2 engine
            paragraphs = text.split("\n")
            translated_paragraphs = ct2.translate_batch(paragraphs, target_lang=target_lang, source_lang=source_lang)
            return "\n".join(translated_paragraphs)
        except Exception as e:
            logger.warning(f"CTranslate2 offline translation failed, falling back to online: {e}")

    # Fallback to online providers
    chunks = _chunk_text(text, max_chars=850)
    if len(chunks) == 1:
        return _translate_single_chunk(chunks[0], target_lang, source_lang)

    translated_chunks: List[str] = []
    for c in chunks:
        if not c.strip():
            translated_chunks.append("")
        else:
            translated_chunks.append(_translate_single_chunk(c, target_lang, source_lang))

    sep = "\n" if "\n" in text else " "
    return sep.join(translated_chunks)


def translate_segments(
    segments: List[Dict[str, Any]],
    target_lang: str = "vi",
    source_lang: str = "auto",
) -> List[Dict[str, Any]]:
    """Translate speech segments with preserved start and end timestamps.

    Prioritizes local offline CTranslate2 model for exact 1-to-1 batch translation.
    Falls back to indexed tag batching via online providers when offline model is unavailable.
    """
    if not segments:
        return []

    if source_lang != "auto" and source_lang.lower().startswith(target_lang.lower()[:2]):
        return [dict(s) for s in segments]

    translated_segments: List[Dict[str, Any]] = [dict(s) for s in segments]

    ct2 = get_ctranslate2_translator()
    if ct2.is_downloaded():
        try:
            texts = [s.get("text", "").strip() for s in segments]
            translated_texts = ct2.translate_batch(texts, target_lang=target_lang, source_lang=source_lang)
            for i, tr_text in enumerate(translated_texts):
                translated_segments[i]["text"] = tr_text
            return translated_segments
        except Exception as e:
            logger.warning(f"CTranslate2 segment translation failed, falling back to online: {e}")

    # Fallback: Online providers using tagged block batching
    tag_regex = re.compile(r'\[\s*#\s*(\d+)\s*#\s*\]\s*(.*?)(?=\s*\[\s*#\s*\d+\s*#\s*\]|$)', re.DOTALL)
    max_batch_chars = 700
    max_batch_count = 12

    i = 0
    total_segs = len(segments)
    while i < total_segs:
        batch_indices: List[int] = []
        batch_chars = 0

        while i < total_segs and len(batch_indices) < max_batch_count:
            seg_text = segments[i].get("text", "").strip()
            item_len = len(seg_text) + 12
            if batch_indices and (batch_chars + item_len > max_batch_chars):
                break
            batch_indices.append(i)
            batch_chars += item_len
            i += 1

        non_empty = [idx for idx in batch_indices if segments[idx].get("text", "").strip()]
        if not non_empty:
            for idx in batch_indices:
                translated_segments[idx]["text"] = ""
            continue

        tagged_lines = [f"[#{idx}#] {segments[idx].get('text', '').strip()}" for idx in batch_indices]
        tagged_block = "\n".join(tagged_lines)

        try:
            translated_block = _translate_single_chunk(tagged_block, target_lang, source_lang)
            matches = dict(tag_regex.findall(translated_block))

            for idx in batch_indices:
                str_idx = str(idx)
                if str_idx in matches and matches[str_idx].strip():
                    translated_segments[idx]["text"] = matches[str_idx].strip()
                else:
                    orig_text = segments[idx].get("text", "").strip()
                    if orig_text:
                        translated_segments[idx]["text"] = _translate_single_chunk(orig_text, target_lang, source_lang)
                    else:
                        translated_segments[idx]["text"] = ""
        except Exception as e:
            logger.warning(f"Batch translation failed for indices {batch_indices}: {e}")
            for idx in batch_indices:
                orig_text = segments[idx].get("text", "").strip()
                try:
                    translated_segments[idx]["text"] = _translate_single_chunk(orig_text, target_lang, source_lang) if orig_text else ""
                except Exception:
                    translated_segments[idx]["text"] = orig_text

    return translated_segments
