import logging
import re
import unicodedata

from langdetect import DetectorFactory, detect, lang_detect_exception

logger = logging.getLogger(__name__)
DetectorFactory.seed = 0

ITALIAN_LANGUAGE_CODES = {"it", "ita", "italian", "italiano"}
TTS_SAFE_PUNCTUATION = frozenset(".,;:!?¿¡'\"“”‘’()[]{}-–—/")

TTS_SYMBOL_SUBSTITUTIONS = {
    "default": (
        (re.compile(r"°\s*[Cc]\b"), " degrees celsius"),
        (re.compile(r"°\s*[Ff]\b"), " degrees fahrenheit"),
        (re.compile(r"°"), " degrees"),
    ),
    "it": (
        (re.compile(r"°\s*[Cc]\b"), " gradi celsius"),
        (re.compile(r"°\s*[Ff]\b"), " gradi fahrenheit"),
        (re.compile(r"°"), " gradi"),
    ),
}


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


def normalize_text_for_tts(text: str, language: str | None = None) -> str:
    """
    Normalize model output before passing it to a TTS engine.

    Punctuation is preserved because it guides prosody, the percent sign is
    preserved because TTS engines usually handle it well, and unsupported
    Unicode symbols are removed so they are not spoken literally.
    """
    clean_text = unicodedata.normalize("NFKC", text).strip()
    if not clean_text:
        return ""

    clean_text = substitute_tts_symbols(clean_text, language)
    clean_text = remove_unsupported_tts_symbols(clean_text)
    return re.sub(r"\s+", " ", clean_text).strip()


def substitute_tts_symbols(text: str, language: str | None = None) -> str:
    substitutions = TTS_SYMBOL_SUBSTITUTIONS[
        "it" if _is_italian_language(language) else "default"
    ]
    normalized_text = text
    for pattern, replacement in substitutions:
        normalized_text = pattern.sub(replacement, normalized_text)
    return normalized_text


def remove_unsupported_tts_symbols(text: str) -> str:
    normalized_chars: list[str] = []
    for char in text:
        if _is_tts_safe_char(char, normalized_chars):
            normalized_chars.append(char)
        elif normalized_chars and not normalized_chars[-1].isspace():
            normalized_chars.append(" ")

    return "".join(normalized_chars)


def _is_italian_language(language: str | None) -> bool:
    return bool(language and language.strip().lower() in ITALIAN_LANGUAGE_CODES)


def _is_tts_safe_char(char: str, previous_chars: list[str]) -> bool:
    if char == "%":
        return True

    category = unicodedata.category(char)
    if char.isspace() or category[0] in {"L", "N"}:
        return True
    if char in TTS_SAFE_PUNCTUATION:
        return True
    if category in {"Mc", "Me", "Mn"}:
        return bool(
            previous_chars and unicodedata.category(previous_chars[-1])[0] == "L"
        )
    return False
