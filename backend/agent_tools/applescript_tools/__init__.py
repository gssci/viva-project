from .calendar import (
    calendar_tools,
    create_mac_calendar_event,
    delete_mac_calendar_event,
    list_mac_calendar_events,
    list_mac_calendars,
    update_mac_calendar_event,
)
from .context import (
    context_tools,
    get_active_safari_url,
    get_clipboard_content,
    get_finder_selection_path,
    set_clipboard_content,
)
from .media_files import (
    control_mac_music,
    empty_mac_trash,
    media_file_tools,
)
from .productivity import (
    create_mac_note,
    productivity_tools,
    send_imessage,
)
from .reminders import (
    complete_mac_reminder,
    create_mac_reminder,
    delete_mac_reminder,
    list_mac_reminders,
    reminder_tools,
)
from .system import (
    set_mac_dark_mode,
    set_mac_volume,
    system_tools,
    toggle_mac_mute,
)


all_mac_tools = [
    *system_tools,
    *productivity_tools,
    *reminder_tools,
    *calendar_tools,
    *context_tools,
    *media_file_tools,
]


__all__ = [
    "all_mac_tools",
    "calendar_tools",
    "context_tools",
    "media_file_tools",
    "productivity_tools",
    "reminder_tools",
    "system_tools",
    "complete_mac_reminder",
    "control_mac_music",
    "create_mac_calendar_event",
    "create_mac_note",
    "create_mac_reminder",
    "delete_mac_calendar_event",
    "delete_mac_reminder",
    "empty_mac_trash",
    "get_active_safari_url",
    "get_clipboard_content",
    "get_finder_selection_path",
    "list_mac_calendar_events",
    "list_mac_calendars",
    "list_mac_reminders",
    "send_imessage",
    "set_clipboard_content",
    "set_mac_dark_mode",
    "set_mac_volume",
    "toggle_mac_mute",
    "update_mac_calendar_event",
]
