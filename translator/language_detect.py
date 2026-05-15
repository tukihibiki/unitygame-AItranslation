"""Language detection for Japanese/Chinese text gating.

Primary: fastText lid.176.bin model (highest accuracy, requires 130MB model file)
Fallback: Unicode character-range analysis (zero-dependency, works immediately)
"""

import logging
import os

logger = logging.getLogger(__name__)

_MODEL: object | None = None
_MODEL_LOADED = False
_MODEL_FAILED = False

# Unicode ranges for Japanese and Chinese
HIRAGANA = (0x3040, 0x309F)
KATAKANA = (0x30A0, 0x30FF)
CJK_UNIFIED = (0x4E00, 0x9FFF)
CJK_EXT_A = (0x3400, 0x4DBF)
JAPANESE_SPECIFIC = {0x3005, 0x3006, 0x3007, 0x30FB, 0x30FC, 0x3001, 0x3002}
JAPANESE_KANA_BLOCK = {0x3040, 0x3041, 0x3044, 0x3046, 0x3048, 0x304A}  # Sampling of hiragana


def _load_model(path: str):
    global _MODEL, _MODEL_LOADED, _MODEL_FAILED
    if _MODEL_LOADED or _MODEL_FAILED:
        return
    try:
        import fasttext
        _MODEL = fasttext.load_model(path)
        _MODEL_LOADED = True
        logger.info(f"fastText model loaded from {path}")
    except ImportError:
        _MODEL_FAILED = True
        logger.warning("fasttext not available, using character-range fallback")
    except FileNotFoundError:
        _MODEL_FAILED = True
        logger.warning(f"Model file not found: {path}, using character-range fallback")
    except Exception as e:
        _MODEL_FAILED = True
        logger.warning(f"Failed to load fastText model: {e}, using character-range fallback")


def _has_japanese_chars(text: str) -> bool:
    """Check if text contains Japanese-specific characters (hiragana/katakana)."""
    for ch in text:
        cp = ord(ch)
        if HIRAGANA[0] <= cp <= HIRAGANA[1]:
            return True
        if KATAKANA[0] <= cp <= KATAKANA[1]:
            return True
    return False


def _has_cjk_chars(text: str) -> bool:
    """Check if text contains CJK unified ideographs."""
    for ch in text:
        cp = ord(ch)
        if CJK_UNIFIED[0] <= cp <= CJK_UNIFIED[1]:
            return True
        if CJK_EXT_A[0] <= cp <= CJK_EXT_A[1]:
            return True
    return False


def is_japanese(text: str, model_path: str = "./lid.176.bin", min_confidence: float = 0.7) -> bool:
    """Return True if the text is likely Japanese.

    With fastText model: uses ML-based language detection.
    Without model: uses Unicode range analysis (hiragana/katakana presence).
    """
    if not text or not text.strip():
        return False

    text = text.strip()

    if not _MODEL_LOADED and not _MODEL_FAILED and os.path.exists(model_path):
        _load_model(model_path)

    if _MODEL_LOADED:
        try:
            cleaned = text.replace("\n", " ").replace("\r", " ")
            prediction = _MODEL.predict(cleaned, k=1)
            label = prediction[0][0].replace("__label__", "")
            confidence = prediction[1][0]
            result = label == "ja" and confidence >= min_confidence
            logger.debug(f"fastText: '{text[:40]}' -> {label}/{confidence:.2f} ja={result}")
            return result
        except Exception as e:
            logger.error(f"fastText error: {e}, falling back to char-range")

    # Character-range fallback: Japanese text always has hiragana or katakana
    result = _has_japanese_chars(text)
    logger.debug(f"Char-range: '{text[:40]}' -> japanese={result}")
    return result


def is_chinese(text: str, model_path: str = "./lid.176.bin", min_confidence: float = 0.7) -> bool:
    """Return True if the text is already in Chinese (and NOT Japanese).

    Distinguishes Chinese from Japanese by: text has CJK characters but NO hiragana/katakana.
    """
    if not text or not text.strip():
        return False

    text = text.strip()

    if not _MODEL_LOADED and not _MODEL_FAILED and os.path.exists(model_path):
        _load_model(model_path)

    if _MODEL_LOADED:
        try:
            cleaned = text.replace("\n", " ").replace("\r", " ")
            prediction = _MODEL.predict(cleaned, k=1)
            label = prediction[0][0].replace("__label__", "")
            confidence = prediction[1][0]
            return label == "zh" and confidence >= min_confidence
        except Exception:
            pass

    # Character-range fallback: Chinese has CJK chars but NO hiragana/katakana
    if _has_japanese_chars(text):
        return False  # Has kana -> Japanese, not Chinese
    return _has_cjk_chars(text)  # Has Chinese characters but no kana -> Chinese
