from typing import Optional

from langchain_core.tools import tool

from .core import run_applescript


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


reminder_tools = [
    create_mac_reminder,
    list_mac_reminders,
    complete_mac_reminder,
    delete_mac_reminder,
]
