import subprocess
from typing import Optional
from langchain_core.tools import tool

def run_applescript(script: str) -> str:
    """
    Helper function to execute AppleScript code using osascript.
    Note: This is NOT a LangChain tool, do not decorate it. It is used internally by the tools.
    """
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Script execution error: {e.stderr.strip()}"


# --- SYSTEM MANAGEMENT ---

@tool
def set_mac_volume(level: int) -> str:
    """
    Sets the system volume of the Mac.
    Call this tool when the user asks to change, raise, or lower the volume to a specific percentage.
    
    Args:
        level: Volume level from 0 to 100.
    """
    level = max(0, min(100, level))
    script = f'set volume output volume {level}'
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
    script = f'set volume {state} output muted'
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


# --- PRODUCTIVITY & COMMUNICATION ---

@tool
def send_imessage(contact: str, message: str) -> str:
    """
    Sends a message via the Messages app (iMessage or SMS).
    Call this tool when the user asks to text, message, or iMessage someone.
    
    Args:
        contact: Phone number (e.g., "+1234567890") or Apple ID email of the contact.
        message: The text message to send.
    """
    safe_message = message.replace('"', '\\"')
    script = f'''
    tell application "Messages"
        set targetBuddy to buddy "{contact}"
        send "{safe_message}" to targetBuddy
    end tell
    '''
    result = run_applescript(script)
    if "Error" in result:
        return f"Failed to send the message. Ensure the contact {contact} is correct or exists."
    return f"Message successfully sent to {contact}."

@tool
def create_mac_note(text: str) -> str:
    """
    Creates a new note in the Apple Notes app. 
    Call this tool when the user asks to write down a note, save a thought to Notes, or draft a document.
    The first line of the text automatically becomes the title.
    
    Args:
        text: The body of the note, preferably in plain text or basic HTML.
    """
    safe_text = text.replace('"', '\\"').replace('\n', '<br>')
    script = f'''
    tell application "Notes"
        tell account "iCloud" -- Replace with "On My Mac" if you don't use iCloud
            make new note with properties {{body:"{safe_text}"}}
        end tell
    end tell
    '''
    run_applescript(script)
    return "Note successfully created."


# --- ADVANCED REMINDERS MANAGEMENT ---

@tool
def create_mac_reminder(name: str, body: Optional[str] = "") -> str:
    """
    Creates a new reminder in the Apple Reminders app.
    Call this tool when the user asks to set a reminder, add a task to their to-do list, or remember something.
    
    Args:
        name: The title or main subject of the reminder.
        body: (Optional) Extra notes or details to add to the reminder.
    """
    safe_name = name.replace('"', '\\"')
    safe_body = body.replace('"', '\\"') if body else ""
    
    script = f'''
    tell application "Reminders"
        make new reminder with properties {{name:"{safe_name}", body:"{safe_body}"}}
    end tell
    '''
    run_applescript(script)
    return f"Reminder '{name}' successfully created."

@tool
def list_mac_reminders(list_name: Optional[str] = None) -> str:
    """
    Retrieves all pending/incomplete reminders from the Apple Reminders app.
    Call this tool when the user asks what they have to do, or wants to check their reminders/tasks.
    
    Args:
        list_name: (Optional) If specified, searches only within that specific list (e.g., "Work", "Groceries").
    """
    list_filter = f'of list "{list_name}"' if list_name else ""
    script = f'''
    tell application "Reminders"
        set output to ""
        try
            set incompleteReminders to (every reminder {list_filter} whose completed is false)
            if (count of incompleteReminders) = 0 then return "No pending reminders."
            
            repeat with r in incompleteReminders
                set output to output & "- " & name of r & "\\n"
            end repeat
            return output
        on error
            return "Error: The specified list might not exist."
        end try
    end tell
    '''
    return run_applescript(script)

@tool
def complete_mac_reminder(name_query: str) -> str:
    """
    Marks a reminder as completed by searching for its name.
    Call this tool when the user says they finished a task or asks to check off a reminder.
    
    Args:
        name_query: A keyword or the exact name of the reminder to complete.
    """
    safe_query = name_query.replace('"', '\\"')
    script = f'''
    tell application "Reminders"
        set targetReminders to (every reminder whose name contains "{safe_query}" and completed is false)
        if (count of targetReminders) = 0 then
            return "No active reminder found with this name."
        end if
        
        set r to item 1 of targetReminders
        set completed of r to true
        return "Reminder '" & name of r & "' marked as completed."
    end tell
    '''
    return run_applescript(script)

@tool
def delete_mac_reminder(name_query: str) -> str:
    """
    Permanently deletes a reminder (completed or not) by searching for its name.
    Call this tool when the user asks to delete, erase, or completely remove a reminder.
    
    Args:
        name_query: A keyword or the exact name of the reminder to delete.
    """
    safe_query = name_query.replace('"', '\\"')
    script = f'''
    tell application "Reminders"
        set targetReminders to (every reminder whose name contains "{safe_query}")
        if (count of targetReminders) = 0 then
            return "No reminder found with this name."
        end if
        
        set rName to name of item 1 of targetReminders
        delete item 1 of targetReminders
        return "Reminder '" & rName & "' permanently deleted."
    end tell
    '''
    return run_applescript(script)


# --- CONTEXT READING (Clipboard, Browser, Finder) ---

@tool
def get_clipboard_content() -> str:
    """
    Reads the current text content from the Mac Clipboard.
    Call this tool when the user asks you to read, summarize, translate, or interact with the text they just copied.
    """
    script = 'the clipboard as text'
    result = run_applescript(script)
    if "Error" in result:
        return "No text found in the clipboard."
    return result

@tool
def set_clipboard_content(text: str) -> str:
    """
    Overwrites the Mac clipboard with the provided text.
    Call this tool when the user asks you to copy your response or generate text directly to their clipboard.
    
    Args:
        text: The text to copy to the clipboard.
    """
    safe_text = text.replace('"', '\\"').replace('\n', '\\n')
    script = f'set the clipboard to "{safe_text}"'
    run_applescript(script)
    return "Text successfully copied to the clipboard."

@tool
def get_active_safari_url() -> str:
    """
    Gets the URL and title of the currently active, frontmost tab in Safari.
    Call this tool when the user asks questions about "this article", "the page I'm reading", or asks you to scrape their current context.
    """
    script = '''
    tell application "Safari"
        if it is running then
            set currentTab to current tab of front window
            set tabURL to URL of currentTab
            set tabName to name of currentTab
            return tabName & "\\n" & tabURL
        else
            return "Safari is not currently running."
        end if
    end tell
    '''
    return run_applescript(script)

@tool
def get_finder_selection_path() -> str:
    """
    Returns the POSIX path of the file or folder currently selected in Finder.
    Call this tool when the user asks you to read, modify, or do something with "the selected file" or "this file in Finder".
    """
    script = '''
    tell application "Finder"
        set selectedItems to selection
        if (count of selectedItems) = 0 then
            return "No items selected in Finder."
        end if
        set theItem to item 1 of selectedItems
        return POSIX path of (theItem as alias)
    end tell
    '''
    return run_applescript(script)


# --- ENTERTAINMENT & FILES ---

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

all_mac_tools = [
    set_mac_volume, 
    toggle_mac_mute, 
    set_mac_dark_mode,
    send_imessage, 
    create_mac_note, 
    create_mac_reminder,
    list_mac_reminders, 
    complete_mac_reminder, 
    delete_mac_reminder,
    get_clipboard_content, 
    set_clipboard_content, 
    get_active_safari_url,
    get_finder_selection_path, 
    control_mac_music, 
    empty_mac_trash
]
