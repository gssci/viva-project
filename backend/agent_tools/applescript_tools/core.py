import datetime as dt
import subprocess
from typing import Optional


APPLESCRIPT_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def run_applescript(script: str) -> str:
    """
    Helper function to execute AppleScript code using osascript.
    Note: This is NOT a LangChain tool, do not decorate it. It is used internally by the tools.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Script execution error: {e.stderr.strip()}"


def escape_applescript_string(value: Optional[str]) -> str:
    """Escapes user-provided text for use inside an AppleScript string literal."""
    if not value:
        return ""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def parse_calendar_datetime(value: str) -> dt.datetime:
    """
    Parses local calendar date/time input.
    Prefer ISO formats, for example: 2026-04-28, 2026-04-28 14:30,
    2026-04-28T14:30:00, or 2026-04-28T14:30:00+02:00.
    """
    text = value.strip()
    if not text:
        raise ValueError("Date/time cannot be empty.")

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
        accepted_formats = [
            "%Y/%m/%d",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %I:%M %p",
            "%Y-%m-%d %I %p",
        ]
        for date_format in accepted_formats:
            try:
                parsed = dt.datetime.strptime(text, date_format)
                break
            except ValueError:
                continue

        if parsed is None:
            raise ValueError(
                "Use an ISO-like date/time, such as 2026-04-28 14:30."
            )

    if parsed.tzinfo:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def applescript_date_assignment(variable_name: str, value: dt.datetime) -> str:
    """Builds AppleScript statements that assign a specific local date/time."""
    seconds_since_midnight = (
        value.hour * 3600
        + value.minute * 60
        + value.second
    )
    month_name = APPLESCRIPT_MONTHS[value.month - 1]
    return f'''
        set {variable_name} to current date
        set day of {variable_name} to 1
        set year of {variable_name} to {value.year}
        set month of {variable_name} to {month_name}
        set day of {variable_name} to {value.day}
        set time of {variable_name} to {seconds_since_midnight}
    '''


def calendar_range(
    start_datetime: Optional[str],
    end_datetime: Optional[str],
    default_days: int,
) -> tuple[dt.datetime, dt.datetime]:
    start = (
        parse_calendar_datetime(start_datetime)
        if start_datetime
        else dt.datetime.combine(dt.date.today(), dt.time.min)
    )
    end = (
        parse_calendar_datetime(end_datetime)
        if end_datetime
        else start + dt.timedelta(days=default_days)
    )
    if end <= start:
        raise ValueError("End date/time must be after the start date/time.")
    return start, end


def calendar_target_script(calendar_name: Optional[str]) -> str:
    if calendar_name:
        safe_calendar_name = escape_applescript_string(calendar_name)
        return f'set targetCalendar to calendar "{safe_calendar_name}"'
    return "set targetCalendar to first calendar whose writable is true"


def calendars_to_search_script(calendar_name: Optional[str]) -> str:
    if calendar_name:
        safe_calendar_name = escape_applescript_string(calendar_name)
        return f'set calendarsToSearch to {{calendar "{safe_calendar_name}"}}'
    return "set calendarsToSearch to every calendar"
