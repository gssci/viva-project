import datetime as dt
from typing import Optional

from langchain_core.tools import tool

from .core import (
    applescript_date_assignment,
    applescript_list,
    calendar_range,
    calendar_target_script,
    calendars_to_search_script,
    escape_applescript_string,
    parse_csv_values,
    parse_calendar_datetime,
    run_applescript,
)


def _calendar_attendee_script(attendee_emails: Optional[str], event_variable: str = "newEvent") -> str:
    attendees = parse_csv_values(attendee_emails)
    if not attendees:
        return ""
    return f'''
        set attendeeEmails to {applescript_list(attendees)}
        repeat with attendeeEmail in attendeeEmails
            make new attendee at end of attendees of {event_variable} with properties {{email:(attendeeEmail as text)}}
        end repeat
    '''


def _calendar_alarm_script(alarm_minutes_before: Optional[int], event_variable: str = "newEvent") -> str:
    if alarm_minutes_before is None:
        return ""
    if alarm_minutes_before < 0 or alarm_minutes_before > 10080:
        raise ValueError("Alarm minutes must be between 0 and 10080.")
    return f'''
        make new display alarm at end of display alarms of {event_variable} with properties {{trigger interval:-{alarm_minutes_before}}}
    '''


@tool
def list_mac_calendars() -> str:
    """
    Lists the available calendars in the Apple Calendar app.
    Call this tool when the user asks what calendars they have or when you need a calendar name before creating an event.
    """
    script = '''
    tell application "Calendar"
        set output to ""
        repeat with c in calendars
            set calendarName to name of c
            try
                set writableState to writable of c
                if writableState then
                    set output to output & "- " & calendarName & " (writable)" & "\\n"
                else
                    set output to output & "- " & calendarName & " (read-only)" & "\\n"
                end if
            on error
                set output to output & "- " & calendarName & "\\n"
            end try
        end repeat
        if output is "" then return "No calendars found."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def create_mac_calendar_event(
    title: str,
    start_datetime: str,
    end_datetime: Optional[str] = None,
    calendar_name: Optional[str] = None,
    location: Optional[str] = "",
    notes: Optional[str] = "",
    event_url: Optional[str] = "",
    attendee_emails: Optional[str] = "",
    alarm_minutes_before: Optional[int] = None,
    all_day: bool = False,
) -> str:
    """
    Creates an event in Apple Calendar.
    Call this tool when the user asks to add, schedule, book, or put an event on their calendar.
    Prefer ISO-like local date/time strings, such as "2026-04-28 14:30".

    Args:
        title: The event title.
        start_datetime: Event start as a local date/time string, preferably ISO-like.
        end_datetime: (Optional) Event end as a local date/time string. For all-day events, this is treated as the last visible day.
        calendar_name: (Optional) The Calendar list name. Uses the first writable calendar if omitted.
        location: (Optional) Event location.
        notes: (Optional) Event notes or description.
        event_url: (Optional) URL associated with the event.
        attendee_emails: (Optional) Comma-separated attendee email addresses.
        alarm_minutes_before: (Optional) Display alarm minutes before start, from 0 to 10080.
        all_day: True to create an all-day event.
    """
    if not title.strip():
        return "Calendar event title cannot be empty."

    try:
        start = parse_calendar_datetime(start_datetime)
        if all_day:
            start = dt.datetime.combine(start.date(), dt.time.min)
            if end_datetime:
                parsed_end = parse_calendar_datetime(end_datetime)
                end = dt.datetime.combine(parsed_end.date(), dt.time.min)
                if end <= start:
                    end = start + dt.timedelta(days=1)
                else:
                    end = end + dt.timedelta(days=1)
            else:
                end = start + dt.timedelta(days=1)
        else:
            end = (
                parse_calendar_datetime(end_datetime)
                if end_datetime
                else start + dt.timedelta(hours=1)
            )
            if end <= start:
                return "End date/time must be after the start date/time."
        alarm_script = _calendar_alarm_script(alarm_minutes_before)
    except ValueError as exc:
        return f"Invalid calendar input: {exc}"

    safe_title = escape_applescript_string(title)
    safe_location = escape_applescript_string(location)
    safe_notes = escape_applescript_string(notes)
    safe_url = escape_applescript_string(event_url)
    all_day_value = "true" if all_day else "false"
    attendee_script = _calendar_attendee_script(attendee_emails)

    script = f'''
    tell application "Calendar"
        {calendar_target_script(calendar_name)}
        {applescript_date_assignment("eventStart", start)}
        {applescript_date_assignment("eventEnd", end)}
        tell targetCalendar
            set newEvent to make new event with properties {{summary:"{safe_title}", start date:eventStart, end date:eventEnd, allday event:{all_day_value}, location:"{safe_location}", description:"{safe_notes}", url:"{safe_url}"}}
        end tell
        {attendee_script}
        {alarm_script}
        return "Calendar event '" & summary of newEvent & "' created in " & name of targetCalendar & "."
    end tell
    '''
    return run_applescript(script)


@tool
def list_mac_calendar_events(
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    calendar_name: Optional[str] = None,
    query: Optional[str] = None,
    max_results: int = 20,
) -> str:
    """
    Lists Apple Calendar events in a date range.
    Call this tool when the user asks what is on their calendar, asks about upcoming events, or wants to find calendar events.
    If no date range is supplied, it lists events from today through the next 7 days.

    Args:
        start_datetime: (Optional) Range start as a local date/time string.
        end_datetime: (Optional) Range end as a local date/time string.
        calendar_name: (Optional) Search only this calendar.
        query: (Optional) Match event titles containing this text.
        max_results: Maximum number of events to return, from 1 to 50.
    """
    try:
        range_start, range_end = calendar_range(start_datetime, end_datetime, 7)
    except ValueError as exc:
        return f"Invalid calendar date/time: {exc}"

    max_results = max(1, min(50, max_results))
    safe_query = escape_applescript_string(query)
    event_filter = (
        f'every event of c whose start date is greater than or equal to rangeStart and start date is less than rangeEnd and summary contains "{safe_query}"'
        if query
        else "every event of c whose start date is greater than or equal to rangeStart and start date is less than rangeEnd"
    )

    script = f'''
    tell application "Calendar"
        {calendars_to_search_script(calendar_name)}
        {applescript_date_assignment("rangeStart", range_start)}
        {applescript_date_assignment("rangeEnd", range_end)}
        set output to ""
        set eventCount to 0

        repeat with c in calendarsToSearch
            set calendarName to name of c
            set matchingEvents to ({event_filter})
            repeat with eventItem in matchingEvents
                set eventCount to eventCount + 1
                set output to output & "- " & summary of eventItem & " | " & (start date of eventItem as string) & " - " & (end date of eventItem as string) & " | " & calendarName
                try
                    set eventUid to uid of eventItem
                    set output to output & " | uid: " & eventUid
                end try
                set output to output & "\\n"
                if eventCount is greater than or equal to {max_results} then return output
            end repeat
        end repeat

        if output is "" then return "No calendar events found."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def update_mac_calendar_event(
    event_query: str,
    new_title: Optional[str] = None,
    new_start_datetime: Optional[str] = None,
    new_end_datetime: Optional[str] = None,
    new_location: Optional[str] = None,
    new_notes: Optional[str] = None,
    new_url: Optional[str] = None,
    add_attendee_emails: Optional[str] = None,
    alarm_minutes_before: Optional[int] = None,
    all_day: Optional[bool] = None,
    calendar_name: Optional[str] = None,
    search_start_datetime: Optional[str] = None,
    search_end_datetime: Optional[str] = None,
) -> str:
    """
    Updates a single Apple Calendar event found by title text within a search range.
    Call this tool when the user asks to rename, move, reschedule, or edit a calendar event.
    If the search range is omitted, events from today through the next 365 days are searched.

    Args:
        event_query: Text that appears in the event title.
        new_title: (Optional) Replacement event title.
        new_start_datetime: (Optional) Replacement start date/time.
        new_end_datetime: (Optional) Replacement end date/time.
        new_location: (Optional) Replacement location. Use an empty string to clear it.
        new_notes: (Optional) Replacement notes. Use an empty string to clear them.
        new_url: (Optional) Replacement event URL. Use an empty string to clear it.
        add_attendee_emails: (Optional) Comma-separated attendee emails to add.
        alarm_minutes_before: (Optional) Add a display alarm this many minutes before start.
        all_day: (Optional) True or False to change whether the event is all-day.
        calendar_name: (Optional) Search only this calendar.
        search_start_datetime: (Optional) Search range start. Defaults to today.
        search_end_datetime: (Optional) Search range end. Defaults to 365 days after the search start.
    """
    if not event_query.strip():
        return "Calendar event search text cannot be empty."

    if not any(
        value is not None
        for value in [
            new_title,
            new_start_datetime,
            new_end_datetime,
            new_location,
            new_notes,
            new_url,
            add_attendee_emails,
            alarm_minutes_before,
            all_day,
        ]
    ):
        return "No calendar event changes were provided."
    if new_title is not None and not new_title.strip():
        return "New calendar event title cannot be empty."
    if add_attendee_emails is not None and not add_attendee_emails.strip():
        return "Attendee email list cannot be empty."

    try:
        range_start, range_end = calendar_range(
            search_start_datetime,
            search_end_datetime,
            365,
        )
        start = parse_calendar_datetime(new_start_datetime) if new_start_datetime else None
        end = parse_calendar_datetime(new_end_datetime) if new_end_datetime else None

        if all_day is True:
            if start:
                start = dt.datetime.combine(start.date(), dt.time.min)
            if end:
                end = dt.datetime.combine(end.date(), dt.time.min)
                if start and end <= start:
                    end = start + dt.timedelta(days=1)
                else:
                    end = end + dt.timedelta(days=1)
            elif start:
                end = start + dt.timedelta(days=1)
        elif start and end and end <= start:
            return "New end date/time must be after the new start date/time."
        alarm_script = _calendar_alarm_script(alarm_minutes_before, "targetEvent")
    except ValueError as exc:
        return f"Invalid calendar input: {exc}"

    safe_query = escape_applescript_string(event_query)
    update_lines = []
    if new_title is not None:
        update_lines.append(f'set summary of targetEvent to "{escape_applescript_string(new_title)}"')
    if new_location is not None:
        update_lines.append(f'set location of targetEvent to "{escape_applescript_string(new_location)}"')
    if new_notes is not None:
        update_lines.append(f'set description of targetEvent to "{escape_applescript_string(new_notes)}"')
    if new_url is not None:
        update_lines.append(f'set url of targetEvent to "{escape_applescript_string(new_url)}"')
    if all_day is not None:
        update_lines.append(f'set allday event of targetEvent to {"true" if all_day else "false"}')

    date_assignments = ""
    if start:
        date_assignments += applescript_date_assignment("newStart", start)
    if end:
        date_assignments += applescript_date_assignment("newEnd", end)

    if start and not end:
        update_lines.append("set eventDuration to (end date of targetEvent) - (start date of targetEvent)")
        update_lines.append("set start date of targetEvent to newStart")
        update_lines.append("set end date of targetEvent to newStart + eventDuration")
    elif start:
        update_lines.append("set start date of targetEvent to newStart")
    if end:
        update_lines.append("set end date of targetEvent to newEnd")
    if add_attendee_emails:
        update_lines.append(_calendar_attendee_script(add_attendee_emails, "targetEvent"))
    if alarm_script:
        update_lines.append(alarm_script)

    updates_script = "\n        ".join(update_lines)

    script = f'''
    tell application "Calendar"
        {calendars_to_search_script(calendar_name)}
        {applescript_date_assignment("rangeStart", range_start)}
        {applescript_date_assignment("rangeEnd", range_end)}
        {date_assignments}
        set matchingEvents to {{}}

        repeat with c in calendarsToSearch
            set calendarMatches to (every event of c whose start date is greater than or equal to rangeStart and start date is less than rangeEnd and summary contains "{safe_query}")
            repeat with eventItem in calendarMatches
                set end of matchingEvents to eventItem
            end repeat
        end repeat

        if (count of matchingEvents) = 0 then return "No matching calendar event found."
        if (count of matchingEvents) > 1 then return "Multiple matching events found. Please provide a narrower title, calendar, or date range."

        set targetEvent to item 1 of matchingEvents
        {updates_script}
        return "Calendar event '" & summary of targetEvent & "' updated."
    end tell
    '''
    return run_applescript(script)


@tool
def delete_mac_calendar_event(
    event_query: str,
    calendar_name: Optional[str] = None,
    search_start_datetime: Optional[str] = None,
    search_end_datetime: Optional[str] = None,
) -> str:
    """
    Deletes a single Apple Calendar event found by title text within a search range.
    Call this tool when the user asks to remove, delete, or cancel a calendar event.
    If the search range is omitted, events from today through the next 365 days are searched.

    Args:
        event_query: Text that appears in the event title.
        calendar_name: (Optional) Search only this calendar.
        search_start_datetime: (Optional) Search range start. Defaults to today.
        search_end_datetime: (Optional) Search range end. Defaults to 365 days after the search start.
    """
    if not event_query.strip():
        return "Calendar event search text cannot be empty."

    try:
        range_start, range_end = calendar_range(
            search_start_datetime,
            search_end_datetime,
            365,
        )
    except ValueError as exc:
        return f"Invalid calendar date/time: {exc}"

    safe_query = escape_applescript_string(event_query)
    script = f'''
    tell application "Calendar"
        {calendars_to_search_script(calendar_name)}
        {applescript_date_assignment("rangeStart", range_start)}
        {applescript_date_assignment("rangeEnd", range_end)}
        set matchingEvents to {{}}

        repeat with c in calendarsToSearch
            set calendarMatches to (every event of c whose start date is greater than or equal to rangeStart and start date is less than rangeEnd and summary contains "{safe_query}")
            repeat with eventItem in calendarMatches
                set end of matchingEvents to eventItem
            end repeat
        end repeat

        if (count of matchingEvents) = 0 then return "No matching calendar event found."
        if (count of matchingEvents) > 1 then return "Multiple matching events found. Please provide a narrower title, calendar, or date range."

        set targetEvent to item 1 of matchingEvents
        set eventTitle to summary of targetEvent
        delete targetEvent
        return "Calendar event '" & eventTitle & "' deleted."
    end tell
    '''
    return run_applescript(script)


@tool
def show_mac_calendar_event(
    event_query: str,
    calendar_name: Optional[str] = None,
    search_start_datetime: Optional[str] = None,
    search_end_datetime: Optional[str] = None,
) -> str:
    """
    Opens a single matching Apple Calendar event.
    Call this tool when the user asks to show or open a calendar event.

    Args:
        event_query: Text that appears in the event title.
        calendar_name: (Optional) Search only this calendar.
        search_start_datetime: (Optional) Search range start. Defaults to today.
        search_end_datetime: (Optional) Search range end. Defaults to 365 days after the search start.
    """
    if not event_query.strip():
        return "Calendar event search text cannot be empty."
    try:
        range_start, range_end = calendar_range(search_start_datetime, search_end_datetime, 365)
    except ValueError as exc:
        return f"Invalid calendar date/time: {exc}"

    safe_query = escape_applescript_string(event_query)
    script = f'''
    tell application "Calendar"
        {calendars_to_search_script(calendar_name)}
        {applescript_date_assignment("rangeStart", range_start)}
        {applescript_date_assignment("rangeEnd", range_end)}
        set matchingEvents to {{}}
        repeat with c in calendarsToSearch
            set calendarMatches to (every event of c whose start date is greater than or equal to rangeStart and start date is less than rangeEnd and summary contains "{safe_query}")
            repeat with eventItem in calendarMatches
                set end of matchingEvents to eventItem
            end repeat
        end repeat
        if (count of matchingEvents) = 0 then return "No matching calendar event found."
        if (count of matchingEvents) > 1 then return "Multiple matching events found. Please provide a narrower title, calendar, or date range."
        show item 1 of matchingEvents
        activate
        return "Calendar event opened."
    end tell
    '''
    return run_applescript(script)


@tool
def check_mac_calendar_conflicts(
    start_datetime: str,
    end_datetime: str,
    calendar_name: Optional[str] = None,
    max_results: int = 20,
) -> str:
    """
    Checks for calendar events that overlap a proposed time range.
    Call this tool before scheduling when the user asks whether they are free or if a time conflicts.

    Args:
        start_datetime: Proposed start date/time.
        end_datetime: Proposed end date/time.
        calendar_name: (Optional) Search only this calendar.
        max_results: Maximum conflicts to return, from 1 to 50.
    """
    try:
        range_start, range_end = calendar_range(start_datetime, end_datetime, 1)
    except ValueError as exc:
        return f"Invalid calendar date/time: {exc}"

    max_results = max(1, min(50, max_results))
    script = f'''
    tell application "Calendar"
        {calendars_to_search_script(calendar_name)}
        {applescript_date_assignment("rangeStart", range_start)}
        {applescript_date_assignment("rangeEnd", range_end)}
        set output to ""
        set eventCount to 0
        repeat with c in calendarsToSearch
            set calendarName to name of c
            set overlappingEvents to (every event of c whose start date is less than rangeEnd and end date is greater than rangeStart)
            repeat with eventItem in overlappingEvents
                set eventCount to eventCount + 1
                set output to output & "- " & summary of eventItem & " | " & (start date of eventItem as string) & " - " & (end date of eventItem as string) & " | " & calendarName & "\\n"
                if eventCount is greater than or equal to {max_results} then return output
            end repeat
        end repeat
        if output is "" then return "No calendar conflicts found."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def find_mac_calendar_free_slots(
    start_datetime: str,
    end_datetime: str,
    duration_minutes: int = 30,
    calendar_name: Optional[str] = None,
    max_results: int = 10,
) -> str:
    """
    Finds free calendar slots within a date/time range.
    Call this tool when the user asks when they are free or to find time for something.

    Args:
        start_datetime: Search range start date/time.
        end_datetime: Search range end date/time.
        duration_minutes: Desired slot duration in minutes.
        calendar_name: (Optional) Search only this calendar.
        max_results: Maximum free slots to return, from 1 to 20.
    """
    if duration_minutes < 5 or duration_minutes > 1440:
        return "Duration must be between 5 and 1440 minutes."
    try:
        range_start, range_end = calendar_range(start_datetime, end_datetime, 1)
    except ValueError as exc:
        return f"Invalid calendar date/time: {exc}"

    max_results = max(1, min(20, max_results))
    slot_seconds = duration_minutes * 60
    script = f'''
    tell application "Calendar"
        {calendars_to_search_script(calendar_name)}
        {applescript_date_assignment("rangeStart", range_start)}
        {applescript_date_assignment("rangeEnd", range_end)}
        set output to ""
        set slotCount to 0
        set cursorTime to rangeStart

        repeat while cursorTime + {slot_seconds} is less than or equal to rangeEnd
            set slotEnd to cursorTime + {slot_seconds}
            set hasConflict to false
            repeat with c in calendarsToSearch
                set overlappingEvents to (every event of c whose start date is less than slotEnd and end date is greater than cursorTime)
                if (count of overlappingEvents) > 0 then set hasConflict to true
            end repeat

            if hasConflict is false then
                set slotCount to slotCount + 1
                set output to output & "- " & (cursorTime as string) & " - " & (slotEnd as string) & "\\n"
                if slotCount is greater than or equal to {max_results} then return output
            end if

            set cursorTime to cursorTime + {slot_seconds}
        end repeat

        if output is "" then return "No free calendar slots found."
        return output
    end tell
    '''
    return run_applescript(script)


calendar_tools = [
    list_mac_calendars,
    create_mac_calendar_event,
    list_mac_calendar_events,
    update_mac_calendar_event,
    delete_mac_calendar_event,
    show_mac_calendar_event,
    check_mac_calendar_conflicts,
    find_mac_calendar_free_slots,
]
