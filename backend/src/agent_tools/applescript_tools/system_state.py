from langchain_core.tools import tool

from .core import escape_applescript_string, run_applescript


SETTINGS_PANES = {
    "accessibility": "x-apple.systempreferences:com.apple.Accessibility-Settings.extension",
    "appearance": "x-apple.systempreferences:com.apple.Appearance-Settings.extension",
    "battery": "x-apple.systempreferences:com.apple.Battery-Settings.extension",
    "bluetooth": "x-apple.systempreferences:com.apple.BluetoothSettings",
    "display": "x-apple.systempreferences:com.apple.Displays-Settings.extension",
    "focus": "x-apple.systempreferences:com.apple.Focus-Settings.extension",
    "keyboard": "x-apple.systempreferences:com.apple.Keyboard-Settings.extension",
    "network": "x-apple.systempreferences:com.apple.Network-Settings.extension",
    "notifications": "x-apple.systempreferences:com.apple.Notifications-Settings.extension",
    "privacy": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension",
    "sound": "x-apple.systempreferences:com.apple.Sound-Settings.extension",
    "wifi": "x-apple.systempreferences:com.apple.Wi-Fi-Settings.extension",
}


@tool
def get_mac_battery_status() -> str:
    """
    Returns battery percentage, power source, and charging status.
    Call this tool when the user asks about battery, charging, or power state.
    """
    script = """
    set batteryInfo to do shell script "pmset -g batt | sed -e 's/^[[:space:]]*//'"
    return batteryInfo
    """
    return run_applescript(script)


@tool
def get_mac_wifi_status() -> str:
    """
    Returns the current Wi-Fi interface, power state, and connected network if available.
    Call this tool when the user asks about Wi-Fi or network state.
    """
    script = """
    set wifiDevice to do shell script "networksetup -listallhardwareports | awk '/Wi-Fi|AirPort/{getline; print $2; exit}'"
    if wifiDevice is "" then return "No Wi-Fi hardware port found."
    set powerState to do shell script "networksetup -getairportpower " & wifiDevice
    set networkName to do shell script "networksetup -getairportnetwork " & wifiDevice & " 2>/dev/null | sed 's/^Current Wi-Fi Network: //'"
    return powerState & "\\nNetwork: " & networkName
    """
    return run_applescript(script)


@tool
def get_frontmost_app_info() -> str:
    """
    Returns the frontmost application name and bundle identifier.
    Call this tool when the user asks what app is active or what they are using.
    """
    script = """
    tell application "System Events"
        set frontProcess to first application process whose frontmost is true
        set appName to name of frontProcess
        set bundleId to bundle identifier of frontProcess
        return appName & " | " & bundleId
    end tell
    """
    return run_applescript(script)


@tool
def get_mac_system_summary() -> str:
    """
    Returns a concise macOS hardware and OS summary.
    Call this tool when the user asks about this Mac or system information.
    """
    script = """
    set osInfo to do shell script "sw_vers | paste -sd '; ' -"
    set modelInfo to do shell script "sysctl -n hw.model"
    set chipInfo to do shell script "sysctl -n machdep.cpu.brand_string 2>/dev/null || true"
    return modelInfo & "\\n" & chipInfo & "\\n" & osInfo
    """
    return run_applescript(script)


@tool
def lock_mac_screen() -> str:
    """
    Locks the Mac screen.
    Call this tool when the user asks to lock their Mac. Does not sleep, restart, or shut down.
    """
    script = 'tell application "System Events" to keystroke "q" using {control down, command down}'
    run_applescript(script)
    return "Mac screen locked."


@tool
def start_mac_screensaver() -> str:
    """
    Starts the macOS screensaver.
    Call this tool when the user asks to start the screensaver.
    """
    script = 'tell application "ScreenSaverEngine" to activate'
    run_applescript(script)
    return "Screensaver started."


@tool
def open_system_settings_pane(pane: str) -> str:
    """
    Opens a supported System Settings pane.
    Call this tool when the user asks to open Mac settings such as Wi-Fi, Bluetooth, Battery, Sound, or Privacy.

    Args:
        pane: One of: accessibility, appearance, battery, bluetooth, display, focus, keyboard, network, notifications, privacy, sound, wifi.
    """
    normalized = pane.strip().lower().replace("wi-fi", "wifi")
    if normalized not in SETTINGS_PANES:
        return f"Unsupported settings pane. Try one of: {', '.join(sorted(SETTINGS_PANES))}."

    safe_uri = escape_applescript_string(SETTINGS_PANES[normalized])
    script = f'open location "{safe_uri}"'
    run_applescript(script)
    return f"Opened {normalized} settings."


system_state_tools = [
    get_mac_battery_status,
    get_mac_wifi_status,
    get_frontmost_app_info,
    get_mac_system_summary,
    lock_mac_screen,
    start_mac_screensaver,
    open_system_settings_pane,
]
