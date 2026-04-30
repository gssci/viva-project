from langchain_core.tools import tool

from .core import run_applescript


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
    safe_text = text.replace('"', '\\"').replace("\n", "<br>")
    script = f'''
    tell application "Notes"
        tell account "iCloud" -- Replace with "On My Mac" if you don't use iCloud
            make new note with properties {{body:"{safe_text}"}}
        end tell
    end tell
    '''
    run_applescript(script)
    return "Note successfully created."


productivity_tools = [
    send_imessage,
    create_mac_note,
]
