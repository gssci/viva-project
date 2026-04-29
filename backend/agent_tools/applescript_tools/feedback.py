from typing import Optional

from langchain_core.tools import tool

from .core import escape_applescript_string, run_applescript


@tool
def show_mac_notification(title: str, message: str, subtitle: Optional[str] = "") -> str:
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


@tool
def speak_mac_text(text: str, voice: Optional[str] = None, wait_until_done: bool = True) -> str:
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

    safe_text = escape_applescript_string(text)
    voice_clause = f' using "{escape_applescript_string(voice)}"' if voice else ""
    waiting_clause = " waiting until completion true" if wait_until_done else ""
    script = f'say "{safe_text}"{voice_clause}{waiting_clause}'
    run_applescript(script)
    return "Spoken feedback completed." if wait_until_done else "Spoken feedback started."


feedback_tools = [
    show_mac_notification,
    speak_mac_text,
]
