from typing import Optional

from langchain_core.tools import tool

from .core import escape_applescript_string, run_applescript
import os
import re
from langdetect import detect

SIRI_VOICE_PREVIEWS_DIR = (
    "/System/Library/PrivateFrameworks/SiriTTSService.framework/"
    "Versions/A/Resources/VoicePreviews"
)

SIRI_DEFAULT_VOICES = {
    "ar-SA": ("samer", 1),
    "da-DK": ("else", 2),
    "de-DE": ("helena", 2),
    "en-AU": ("catherine", 2),
    "en-GB": ("martha", 2),
    "en-IE": ("maeve", 2),
    "en-IN": ("riya", 2),
    "en-US": ("nora", 2),
    "en-ZA": ("leona", 2),
    "es-ES": ("luisa", 2),
    "es-MX": ("carmen", 2),
    "fi-FI": ("suvi", 2),
    "fr-CA": ("sophie", 2),
    "fr-FR": ("marie", 2),
    "he-IL": ("yasmin", 2),
    "it-IT": ("paolo", 1),
    "ja-JP": ("sakura", 2),
    "ko-KR": ("minji", 2),
    "ms-MY": ("ms-MY-A", 2),
    "nb-NO": ("ingrid", 2),
    "nl-NL": ("klaar", 2),
    "pt-BR": ("sandra", 2),
    "pt-PT": ("pt-PT-A", 2),
    "ru-RU": ("yelena", 2),
    "sv-SE": ("tilde", 2),
    "th-TH": ("th-TH-A", 2),
    "tr-TR": ("elif", 2),
    "vi-VN": ("vi-VN-A", 2),
    "zh-CN": ("linfei", 2),
    "zh-HK": ("kayan", 2),
    "zh-TW": ("shufen", 2),
}

SIRI_LANGUAGE_ALIASES = {
    "arabic": "ar-SA",
    "danish": "da-DK",
    "german": "de-DE",
    "de": "de-DE",
    "english": "en-US",
    "english australia": "en-AU",
    "english au": "en-AU",
    "english uk": "en-GB",
    "english gb": "en-GB",
    "english ireland": "en-IE",
    "english india": "en-IN",
    "english us": "en-US",
    "english usa": "en-US",
    "english united states": "en-US",
    "english south africa": "en-ZA",
    "en": "en-US",
    "spanish": "es-ES",
    "spanish spain": "es-ES",
    "spanish mexico": "es-MX",
    "es": "es-ES",
    "finnish": "fi-FI",
    "french": "fr-FR",
    "french canada": "fr-CA",
    "french france": "fr-FR",
    "fr": "fr-FR",
    "hebrew": "he-IL",
    "italian": "it-IT",
    "it": "it-IT",
    "japanese": "ja-JP",
    "ja": "ja-JP",
    "korean": "ko-KR",
    "ko": "ko-KR",
    "malay": "ms-MY",
    "norwegian": "nb-NO",
    "dutch": "nl-NL",
    "portuguese": "pt-BR",
    "portuguese brazil": "pt-BR",
    "portuguese portugal": "pt-PT",
    "pt": "pt-BR",
    "russian": "ru-RU",
    "ru": "ru-RU",
    "swedish": "sv-SE",
    "thai": "th-TH",
    "turkish": "tr-TR",
    "vietnamese": "vi-VN",
    "chinese": "zh-CN",
    "mandarin": "zh-CN",
    "chinese china": "zh-CN",
    "chinese hong kong": "zh-HK",
    "cantonese": "zh-HK",
    "chinese taiwan": "zh-TW",
    "zh": "zh-CN",
}


def _canonical_siri_locale(language: str) -> str | None:
    locale = language.strip().replace("_", "-")
    parts = locale.split("-")
    if len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2:
        return None
    return f"{parts[0].lower()}-{parts[1].upper()}"


def _normalize_siri_language(language: str) -> str | None:
    if not language or not language.strip():
        return None

    direct_locale = _canonical_siri_locale(language)
    if direct_locale in SIRI_DEFAULT_VOICES:
        return direct_locale

    alias = " ".join(re.sub(r"[^a-z0-9]+", " ", language.lower()).split())
    return SIRI_LANGUAGE_ALIASES.get(alias)


def _available_siri_voice(locale: str, preferred_voice: str) -> str:
    if not os.path.isdir(SIRI_VOICE_PREVIEWS_DIR):
        return preferred_voice

    preview_names = sorted(os.listdir(SIRI_VOICE_PREVIEWS_DIR))
    locale_prefix = f"{locale}_"
    voices = [
        preview_name.removeprefix(locale_prefix).removesuffix(".caf")
        for preview_name in preview_names
        if preview_name.startswith(locale_prefix) and preview_name.endswith(".caf")
    ]
    if preferred_voice in voices:
        return preferred_voice
    return voices[0] if voices else preferred_voice


def _supported_siri_languages() -> str:
    return ", ".join(sorted(SIRI_DEFAULT_VOICES))


@tool
def show_mac_notification(
    title: str, message: str, subtitle: Optional[str] = ""
) -> str:
    """
    Shows a macOS notification.
    Call this tool when the user asks to notify them, alert them, or show a local notification.

    Args:
        title: Notification title.
        message: Notification body text.
        subtitle: (Optional) Notification subtitle.
    """
    if not title.strip() or not message.strip():
        return "Notification title and message are required."

    safe_title = escape_applescript_string(title)
    safe_message = escape_applescript_string(message)
    safe_subtitle = escape_applescript_string(subtitle)
    subtitle_clause = f' subtitle "{safe_subtitle}"' if subtitle else ""
    script = f'display notification "{safe_message}" with title "{safe_title}"{subtitle_clause}'
    run_applescript(script)
    return "Notification shown."


def set_siri_language_and_voice(language: str) -> str:
    """
    Changes the default Siri language and selects a matching Siri voice.
    Call this tool when the user asks to change Siri's language, Siri's voice,
    or the default voice language in macOS System Settings.

    Args:
        language: Siri language name or locale code, such as Italian, English, it-IT, or en-US.
    """
    locale = _normalize_siri_language(language)
    if not locale:
        return (
            "Unsupported Siri language. Use a language name or one of these "
            f"locale codes: {_supported_siri_languages()}."
        )

    preferred_voice, gender = SIRI_DEFAULT_VOICES[locale]
    voice = _available_siri_voice(locale, preferred_voice)
    safe_locale = escape_applescript_string(locale)
    safe_voice = escape_applescript_string(voice)
    script = f"""
    set targetLanguage to "{safe_locale}"
    set targetVoice to "{safe_voice}"
    set targetGender to "{gender}"

    do shell script "defaults write com.apple.assistant.backedup " & quoted form of "Session Language" & " -string " & quoted form of targetLanguage
    do shell script "defaults write com.apple.assistant.backedup " & quoted form of "Output Voice" & " -dict Custom -bool true Footprint -int 2 Gender -int " & targetGender & " Language -string " & quoted form of targetLanguage & " Name -string " & quoted form of targetVoice
    do shell script "defaults write com.apple.assistant.backedup SiriAvailability -dict-add siriLocale " & quoted form of targetLanguage

    try
        set modificationTimestamp to do shell script "date -u +%Y-%m-%dT%H:%M:%SZ"
        do shell script "defaults write com.apple.assistant.backedup " & quoted form of "Modification Dates" & " -dict-add " & quoted form of "Session Language" & " -date " & quoted form of modificationTimestamp
        do shell script "defaults write com.apple.assistant.backedup " & quoted form of "Modification Dates" & " -dict-add " & quoted form of "Output Voice" & " -date " & quoted form of modificationTimestamp
    end try

    try
        do shell script "killall assistantd >/dev/null 2>&1 || true"
    end try
    """
    result = run_applescript(script)
    if result.startswith("Script execution error:"):
        return result
    return f"Siri language set to {locale} with voice {voice}."


@tool
def speak_mac_text(
    text: str, voice: Optional[str] = None, wait_until_done: bool = False
) -> str:
    """
    Speaks text aloud using the macOS system voice.
    Call this tool when the user asks you to say, announce, or read something out loud.

    Args:
        text: Text to speak.
        voice: (Optional) macOS voice name.
        wait_until_done: True to wait for speech to finish before returning.
    """
    if not text.strip():
        return "Text to speak cannot be empty."
    language = detect(text)
    print(set_siri_language_and_voice(language=language))
    safe_text = escape_applescript_string(text)
    voice_clause = f' using "{escape_applescript_string(voice)}"' if voice else ""
    waiting_clause = " waiting until completion true" if wait_until_done else ""
    script = f'say "{safe_text}"{voice_clause}{waiting_clause}'
    run_applescript(script)
    return (
        "Spoken feedback completed." if wait_until_done else "Spoken feedback started."
    )


feedback_tools = [
    show_mac_notification,
    speak_mac_text,
]
