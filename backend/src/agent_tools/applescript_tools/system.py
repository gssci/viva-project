from langchain_core.tools import tool

from .core import run_applescript


@tool
def set_mac_volume(level: int) -> str:
    """
    Sets the system volume of the Mac.
    Call this tool when the user asks to change, raise, or lower the volume to a specific percentage.

    Args:
        level: Volume level from 0 to 100.
    """
    level = max(0, min(100, level))
    script = f"set volume output volume {level}"
    run_applescript(script)
    return f"Mac volume set to {level}%."


@tool
def toggle_mac_mute(mute: bool) -> str:
    """
    Mutes or unmutes the Mac system volume.
    Call this tool when the user asks to silence the Mac, mute the audio, or unmute it.

    Args:
        mute: True to mute, False to unmute the audio.
    """
    state = "with" if mute else "without"
    script = f"set volume {state} output muted"
    run_applescript(script)
    return "Mac audio muted." if mute else "Mac audio unmuted."


@tool
def set_mac_dark_mode(enable: bool) -> str:
    """
    Enables or disables Dark Mode on macOS.
    Call this tool when the user asks to switch to dark mode, light mode, or change the system theme.

    Args:
        enable: True to enable Dark Mode, False for Light Mode.
    """
    state = "true" if enable else "false"
    script = f'tell application "System Events" to tell appearance preferences to set dark mode to {state}'
    run_applescript(script)
    return "Dark Mode enabled." if enable else "Light Mode enabled."


system_tools = [
    set_mac_volume,
    toggle_mac_mute,
    set_mac_dark_mode,
]
