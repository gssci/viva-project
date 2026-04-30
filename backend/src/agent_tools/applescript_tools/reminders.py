from typing import Optional

from langchain_core.tools import tool

from .core import (
    applescript_date_assignment,
    escape_applescript_string,
    parse_calendar_datetime,
    run_applescript,
)


def _reminder_target_script(list_name: Optional[str]) -> str:
    if list_name:
        safe_list = escape_applescript_string(list_name)
        return f'set targetList to list "{safe_list}"'
    return "set targetList to default list"


@tool
def list_mac_reminder_lists() -> str:
    """
    Lists the available Apple Reminders lists.
    Call this tool when the user asks what reminder lists they have or where a reminder can be added.
    """
    script = """
    tell application "Reminders"
        set output to ""
        repeat with reminderList in lists
            set output to output & "- " & name of reminderList & "\\n"
        end repeat
        if output is "" then return "No reminder lists found."
        return output
    end tell
    """
    return run_applescript(script)


@tool
def create_mac_reminder(
    name: str,
    body: Optional[str] = "",
    list_name: Optional[str] = None,
    due_datetime: Optional[str] = None,
    priority: int = 0,
    all_day_due_date: bool = False,
) -> str:
    """
    Creates a new reminder in the Apple Reminders app.
    Call this tool when the user asks to set a reminder, add a task to their to-do list, or remember something.

    Args:
        name: The title or main subject of the reminder.
        body: (Optional) Extra notes or details to add to the reminder.
        list_name: (Optional) Reminder list name. Uses the default list if omitted.
        due_datetime: (Optional) Due date/time string, preferably ISO-like.
        priority: Reminder priority, 0 for none, 1-4 high, 5 medium, 6-9 low.
        all_day_due_date: True to set an all-day due date instead of an exact due date/time.
    """
    if not name.strip():
        return "Reminder name cannot be empty."
    if priority < 0 or priority > 9:
        return "Reminder priority must be between 0 and 9."

    due_assignment = ""
    due_property = ""
    if due_datetime:
        try:
            due_date = parse_calendar_datetime(due_datetime)
        except ValueError as exc:
            return f"Invalid reminder due date/time: {exc}"
        due_assignment = applescript_date_assignment("reminderDueDate", due_date)
        property_name = "allday due date" if all_day_due_date else "due date"
        due_property = f", {property_name}:reminderDueDate"

    safe_name = escape_applescript_string(name)
    safe_body = escape_applescript_string(body)

    script = f'''
    tell application "Reminders"
        {_reminder_target_script(list_name)}
        {due_assignment}
        set newReminder to make new reminder at end of reminders of targetList with properties {{name:"{safe_name}", body:"{safe_body}", priority:{priority}{due_property}}}
        return "Reminder '" & name of newReminder & "' created in " & name of targetList & "."
    end tell
    '''
    return run_applescript(script)


@tool
def list_mac_reminders(list_name: Optional[str] = None) -> str:
    """
    Retrieves all pending/incomplete reminders from the Apple Reminders app.
    Call this tool when the user asks what they have to do, or wants to check their reminders/tasks.

    Args:
        list_name: (Optional) If specified, searches only within that specific list (e.g., "Work", "Groceries").
    """
    list_filter = (
        f'of list "{escape_applescript_string(list_name)}"' if list_name else ""
    )
    script = f"""
    tell application "Reminders"
        set output to ""
        try
            set incompleteReminders to (every reminder {list_filter} whose completed is false)
            if (count of incompleteReminders) = 0 then return "No pending reminders."

            repeat with r in incompleteReminders
                set output to output & "- " & name of r
                try
                    set output to output & " | due: " & (due date of r as string)
                end try
                try
                    set output to output & " | priority: " & priority of r
                end try
                try
                    set output to output & " | list: " & name of container of r
                end try
                set output to output & "\\n"
            end repeat
            return output
        on error
            return "Error: The specified list might not exist."
        end try
    end tell
    """
    return run_applescript(script)


@tool
def complete_mac_reminder(name_query: str) -> str:
    """
    Marks a reminder as completed by searching for its name.
    Call this tool when the user says they finished a task or asks to check off a reminder.

    Args:
        name_query: A keyword or the exact name of the reminder to complete.
    """
    safe_query = escape_applescript_string(name_query)
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
    safe_query = escape_applescript_string(name_query)
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


@tool
def update_mac_reminder(
    name_query: str,
    new_name: Optional[str] = None,
    new_body: Optional[str] = None,
    new_list_name: Optional[str] = None,
    new_due_datetime: Optional[str] = None,
    new_priority: Optional[int] = None,
) -> str:
    """
    Updates a single active reminder found by title text.
    Call this tool when the user asks to edit, move, reprioritize, or reschedule a reminder.

    Args:
        name_query: Text that appears in the reminder title.
        new_name: (Optional) Replacement reminder title.
        new_body: (Optional) Replacement notes/body.
        new_list_name: (Optional) Reminder list to move it to.
        new_due_datetime: (Optional) Replacement due date/time string.
        new_priority: (Optional) Replacement priority, 0-9.
    """
    if not name_query.strip():
        return "Reminder search text cannot be empty."
    if not any(
        value is not None
        for value in [new_name, new_body, new_list_name, new_due_datetime, new_priority]
    ):
        return "No reminder changes were provided."
    if new_name is not None and not new_name.strip():
        return "New reminder name cannot be empty."
    if new_list_name is not None and not new_list_name.strip():
        return "New reminder list name cannot be empty."
    if new_due_datetime is not None and not new_due_datetime.strip():
        return "New reminder due date/time cannot be empty."
    if new_priority is not None and (new_priority < 0 or new_priority > 9):
        return "Reminder priority must be between 0 and 9."

    date_assignment = ""
    update_lines = []
    if new_name is not None:
        update_lines.append(
            f'set name of targetReminder to "{escape_applescript_string(new_name)}"'
        )
    if new_body is not None:
        update_lines.append(
            f'set body of targetReminder to "{escape_applescript_string(new_body)}"'
        )
    if new_priority is not None:
        update_lines.append(f"set priority of targetReminder to {new_priority}")
    if new_due_datetime:
        try:
            due_date = parse_calendar_datetime(new_due_datetime)
        except ValueError as exc:
            return f"Invalid reminder due date/time: {exc}"
        date_assignment = applescript_date_assignment("newDueDate", due_date)
        update_lines.append("set due date of targetReminder to newDueDate")
    if new_list_name:
        update_lines.append(
            f'move targetReminder to list "{escape_applescript_string(new_list_name)}"'
        )

    safe_query = escape_applescript_string(name_query)
    updates_script = "\n        ".join(update_lines)
    script = f'''
    tell application "Reminders"
        {date_assignment}
        set matchingReminders to (every reminder whose name contains "{safe_query}" and completed is false)
        if (count of matchingReminders) = 0 then return "No active reminder found with this name."
        if (count of matchingReminders) > 1 then return "Multiple active reminders found. Please provide a narrower name."
        set targetReminder to item 1 of matchingReminders
        {updates_script}
        return "Reminder '" & name of targetReminder & "' updated."
    end tell
    '''
    return run_applescript(script)


@tool
def show_mac_reminder(name_query: str) -> str:
    """
    Opens a single matching active reminder in Reminders.
    Call this tool when the user asks to show or open a reminder.

    Args:
        name_query: Text that appears in the reminder title.
    """
    if not name_query.strip():
        return "Reminder search text cannot be empty."

    safe_query = escape_applescript_string(name_query)
    script = f'''
    tell application "Reminders"
        set matchingReminders to (every reminder whose name contains "{safe_query}" and completed is false)
        if (count of matchingReminders) = 0 then return "No active reminder found with this name."
        if (count of matchingReminders) > 1 then return "Multiple active reminders found. Please provide a narrower name."
        show item 1 of matchingReminders
        activate
        return "Reminder opened."
    end tell
    '''
    return run_applescript(script)


reminder_tools = [
    list_mac_reminder_lists,
    create_mac_reminder,
    list_mac_reminders,
    complete_mac_reminder,
    delete_mac_reminder,
    update_mac_reminder,
    show_mac_reminder,
]
