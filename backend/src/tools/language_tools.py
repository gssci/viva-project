import logging
from langdetect import DetectorFactory, detect, lang_detect_exception

logger = logging.getLogger(__name__)
DetectorFactory.seed = 0


def detect_language(text: str, fallback: str = "other") -> str:
    """
    Detects the input language using langdetect.
    Trusts the output of langdetect and returns the ISO 639-1 language code.
    """
    clean_text = text.strip()
    if not clean_text:
        return fallback

    try:
        return detect(clean_text)
    except lang_detect_exception.LangDetectException:
        return fallback
