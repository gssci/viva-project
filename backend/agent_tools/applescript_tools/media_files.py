from langchain_core.tools import tool

from .core import run_applescript


@tool
def control_mac_music(action: str) -> str:
    """
    Controls media playback in the Apple Music app (formerly iTunes).
    Call this tool when the user asks to play, pause, or skip tracks in their music player.

    Args:
        action: The action to execute. Must be exactly one of: "play", "pause", "playpause", "next track", "previous track".
    """
    valid_actions = ["play", "pause", "playpause", "next track", "previous track"]
    if action not in valid_actions:
        return f"Invalid action. Supported actions are: {', '.join(valid_actions)}"

    script = f'tell application "Music" to {action}'
    run_applescript(script)
    return f"Executed '{action}' command in Music app."


@tool
def empty_mac_trash() -> str:
    """
    Empties the macOS Trash.
    Call this tool when the user asks to empty the trash or permanently delete trashed files.
    """
    script = 'tell application "Finder" to empty trash'
    run_applescript(script)
    return "Trash emptied."


media_file_tools = [
    control_mac_music,
    empty_mac_trash,
]
