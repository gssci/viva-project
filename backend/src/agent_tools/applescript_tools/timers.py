import datetime as dt
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.tools import tool

from .core import escape_applescript_string, run_applescript


MAX_TIMER_SECONDS = 30 * 24 * 60 * 60
DEFAULT_TIMER_LABEL = "Timer"
DEFAULT_NOTIFICATION_SOUND = "Glass"


@dataclass
class ManagedTimer:
    id: str
    label: str
    message: str
    duration_seconds: int
    started_at: dt.datetime
    expires_at: dt.datetime
    sound_name: str
    generation: int = 1
    timer: threading.Timer | None = field(default=None, repr=False)


_active_timers: dict[str, ManagedTimer] = {}
_timer_lock = threading.RLock()


def _local_now() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


def _normalize_label(label: Optional[str]) -> str:
    clean_label = (label or "").strip()
    return clean_label or DEFAULT_TIMER_LABEL


def _normalize_sound_name(sound_name: Optional[str]) -> str:
    clean_sound_name = (sound_name or "").strip()
    return clean_sound_name or DEFAULT_NOTIFICATION_SOUND


def _duration_parts(
    duration_seconds: float | None,
    minutes: float | None,
    hours: float | None,
) -> int:
    total_seconds = 0.0
    if duration_seconds is not None:
        total_seconds += float(duration_seconds)
    if minutes is not None:
        total_seconds += float(minutes) * 60
    if hours is not None:
        total_seconds += float(hours) * 3600

    normalized_seconds = round(total_seconds)
    if normalized_seconds <= 0:
        raise ValueError("Timer duration must be greater than zero seconds.")
    if normalized_seconds > MAX_TIMER_SECONDS:
        raise ValueError("Timer duration cannot be longer than 30 days.")
    return normalized_seconds


def _format_datetime(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(total_seconds: int) -> str:
    seconds = max(0, int(total_seconds))
    days, remainder = divmod(seconds, 24 * 3600)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    return ", ".join(parts)


def _timer_summary(timer: ManagedTimer, now: dt.datetime | None = None) -> str:
    current_time = now or _local_now()
    remaining_seconds = max(0, round((timer.expires_at - current_time).total_seconds()))
    return (
        f"- id: {timer.id} | label: {timer.label} | "
        f"remaining: {_format_duration(remaining_seconds)} | "
        f"ends: {_format_datetime(timer.expires_at)}"
    )


def _show_timer_notification(timer: ManagedTimer) -> None:
    title = escape_applescript_string("Viva Timer")
    label = escape_applescript_string(timer.label)
    message = escape_applescript_string(
        timer.message.strip() or f"{timer.label} is done."
    )
    sound = escape_applescript_string(timer.sound_name)
    sound_clause = f' sound name "{sound}"' if sound else ""
    script = (
        f'display notification "{message}" '
        f'with title "{title}" subtitle "{label}"{sound_clause}'
    )
    run_applescript(script)


def _complete_timer(timer_id: str, generation: int) -> None:
    with _timer_lock:
        timer = _active_timers.get(timer_id)
        if timer is None or timer.generation != generation:
            return
        del _active_timers[timer_id]

    _show_timer_notification(timer)


def _start_timer_thread(timer: ManagedTimer) -> None:
    countdown = threading.Timer(
        timer.duration_seconds,
        _complete_timer,
        args=(timer.id, timer.generation),
    )
    countdown.daemon = True
    timer.timer = countdown
    countdown.start()


def _cancel_timer(timer: ManagedTimer) -> None:
    if timer.timer is not None:
        timer.timer.cancel()


def _matching_timers(timer_reference: str) -> list[ManagedTimer]:
    normalized_reference = timer_reference.strip().lower()
    if not normalized_reference:
        return []

    exact_id_match = _active_timers.get(timer_reference.strip())
    if exact_id_match is not None:
        return [exact_id_match]

    return [
        timer
        for timer in _active_timers.values()
        if normalized_reference in timer.label.lower()
    ]


@tool
def set_timer(
    duration_seconds: float | None = None,
    minutes: float | None = None,
    hours: float | None = None,
    label: Optional[str] = None,
    message: Optional[str] = None,
    sound_name: Optional[str] = DEFAULT_NOTIFICATION_SOUND,
) -> str:
    """
    Starts a new backend-managed timer and alerts the user with a macOS notification when it finishes.
    Call this tool when the user asks to set, start, or create a timer.
    Multiple timers can run at the same time.

    Args:
        duration_seconds: Optional timer duration in seconds.
        minutes: Optional timer duration in minutes.
        hours: Optional timer duration in hours.
        label: Optional human-readable timer name, such as "tea" or "laundry".
        message: Optional notification message shown when the timer finishes.
        sound_name: Optional macOS notification sound name. Defaults to "Glass".
    """
    try:
        normalized_duration = _duration_parts(duration_seconds, minutes, hours)
    except (TypeError, ValueError) as exc:
        return f"Timer not set: {exc}"

    now = _local_now()
    normalized_label = _normalize_label(label)
    normalized_message = (message or "").strip() or f"{normalized_label} is done."
    timer_id = uuid.uuid4().hex[:8]
    timer = ManagedTimer(
        id=timer_id,
        label=normalized_label,
        message=normalized_message,
        duration_seconds=normalized_duration,
        started_at=now,
        expires_at=now + dt.timedelta(seconds=normalized_duration),
        sound_name=_normalize_sound_name(sound_name),
    )

    with _timer_lock:
        _active_timers[timer.id] = timer
        _start_timer_thread(timer)

    return (
        f"Timer set. id: {timer.id} | label: {timer.label} | "
        f"duration: {_format_duration(timer.duration_seconds)} | "
        f"ends: {_format_datetime(timer.expires_at)}"
    )


@tool
def list_timers() -> str:
    """
    Lists all active backend-managed timers with their ids, labels, remaining time, and end times.
    Call this tool when the user asks what timers are running or how much time is left.
    """
    with _timer_lock:
        timers = sorted(_active_timers.values(), key=lambda item: item.expires_at)
        if not timers:
            return "No active timers."

        now = _local_now()
        return "Active timers:\n" + "\n".join(
            _timer_summary(timer, now) for timer in timers
        )


@tool
def cancel_timer(timer_reference: str, cancel_all_matches: bool = False) -> str:
    """
    Cancels one active timer by id or by matching text in its label.
    Call this tool when the user asks to cancel, stop, or delete a timer.

    Args:
        timer_reference: Timer id, or text from the timer label.
        cancel_all_matches: True to cancel every timer whose label matches the reference.
    """
    if not timer_reference.strip():
        return "Timer reference cannot be empty. Use a timer id or label text."

    with _timer_lock:
        matches = _matching_timers(timer_reference)
        if not matches:
            return "No active timer matched that reference."
        if len(matches) > 1 and not cancel_all_matches:
            return (
                "Multiple active timers matched. Provide a timer id or set "
                "cancel_all_matches to true.\n"
                + "\n".join(_timer_summary(timer) for timer in matches)
            )

        cancelled_timers = matches if cancel_all_matches else [matches[0]]
        for timer in cancelled_timers:
            _cancel_timer(timer)
            _active_timers.pop(timer.id, None)

    return "Cancelled timers:\n" + "\n".join(
        f"- id: {timer.id} | label: {timer.label}" for timer in cancelled_timers
    )


@tool
def cancel_all_timers() -> str:
    """
    Cancels every active backend-managed timer.
    Call this tool when the user asks to cancel all timers.
    """
    with _timer_lock:
        timers = list(_active_timers.values())
        if not timers:
            return "No active timers."

        for timer in timers:
            _cancel_timer(timer)
        _active_timers.clear()

    return "All active timers cancelled."


@tool
def update_timer(
    timer_reference: str,
    duration_seconds: float | None = None,
    minutes: float | None = None,
    hours: float | None = None,
    label: Optional[str] = None,
    message: Optional[str] = None,
    sound_name: Optional[str] = None,
) -> str:
    """
    Replaces the remaining duration and/or details for one active timer.
    Call this tool when the user asks to change, rename, extend, shorten, or reset a timer.

    Args:
        timer_reference: Timer id, or text from the timer label.
        duration_seconds: Optional replacement duration in seconds from now.
        minutes: Optional replacement duration in minutes from now.
        hours: Optional replacement duration in hours from now.
        label: Optional replacement label.
        message: Optional replacement notification message.
        sound_name: Optional replacement macOS notification sound name.
    """
    if not timer_reference.strip():
        return "Timer reference cannot be empty. Use a timer id or label text."

    should_replace_duration = any(
        value is not None for value in [duration_seconds, minutes, hours]
    )
    try:
        replacement_duration = (
            _duration_parts(duration_seconds, minutes, hours)
            if should_replace_duration
            else None
        )
    except (TypeError, ValueError) as exc:
        return f"Timer not updated: {exc}"

    if not any(
        value is not None
        for value in [replacement_duration, label, message, sound_name]
    ):
        return "No timer changes were provided."

    with _timer_lock:
        matches = _matching_timers(timer_reference)
        if not matches:
            return "No active timer matched that reference."
        if len(matches) > 1:
            return "Multiple active timers matched. Provide a timer id.\n" + "\n".join(
                _timer_summary(timer) for timer in matches
            )

        timer = matches[0]
        _cancel_timer(timer)

        now = _local_now()
        if replacement_duration is not None:
            timer.duration_seconds = replacement_duration
            timer.started_at = now
            timer.expires_at = now + dt.timedelta(seconds=replacement_duration)
        if label is not None:
            timer.label = _normalize_label(label)
        if message is not None:
            timer.message = message.strip() or f"{timer.label} is done."
        if sound_name is not None:
            timer.sound_name = _normalize_sound_name(sound_name)

        timer.generation += 1
        _start_timer_thread(timer)

    remaining_seconds = max(0, round((timer.expires_at - _local_now()).total_seconds()))
    return (
        f"Timer updated. id: {timer.id} | label: {timer.label} | "
        f"remaining: {_format_duration(remaining_seconds)} | "
        f"ends: {_format_datetime(timer.expires_at)}"
    )


timer_tools = [
    set_timer,
    list_timers,
    cancel_timer,
    cancel_all_timers,
    update_timer,
]
