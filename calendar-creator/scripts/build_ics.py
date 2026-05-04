#!/usr/bin/env python3
"""
Build a combined .ics calendar file from a structured JSON description of
courses, recurring meetings, individual events (assignments/exams), and
holidays.

Usage:
    python3 build_ics.py --input courses.json --output courses.ics

Input JSON schema: see the example in syllabus-to-ics/SKILL.md.

Design notes:
- Class meetings use RRULE (weekly) with UNTIL set to the meeting's last_date.
- Holiday dates that fall on a class meeting day become EXDATE entries on
  that meeting, so the recurring class doesn't appear on a holiday — and
  the holiday itself appears as its own all-day event.
- VALARMs are set per event type from the global default_reminders.
- All times are interpreted in the calendar's timezone (TZID), with a
  VTIMEZONE block included automatically by the icalendar library.
- UIDs are stable per (course, item) so re-imports update rather than duplicate.
"""

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from icalendar import Alarm, Calendar, Event


DAY_CODE_TO_WEEKDAY = {
    "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6,
}


def stable_uid(*parts: str) -> str:
    """Deterministic UID so re-importing the same calendar doesn't duplicate."""
    h = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{h}@syllabus-to-ics"


def parse_time(s: str) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS'."""
    parts = s.split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"Bad time: {s!r}")


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def first_occurrence(start: date, weekday: int) -> date:
    """First date on/after `start` that falls on the given weekday (Mon=0)."""
    delta = (weekday - start.weekday()) % 7
    return start + timedelta(days=delta)


def add_alarm(event: Event, minutes_before: int, summary: str) -> None:
    if minutes_before is None or minutes_before <= 0:
        return
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", summary)
    alarm.add("trigger", timedelta(minutes=-minutes_before))
    event.add_component(alarm)


def build_meeting_event(
    course: dict,
    meeting: dict,
    tz: ZoneInfo,
    holidays_by_date: dict,
    reminder_minutes: int,
) -> Event:
    """Build a single recurring VEVENT for a course meeting."""
    days = meeting["days"]
    if not days:
        raise ValueError(
            f"Meeting for {course.get('code')} has no days listed"
        )

    start_t = parse_time(meeting["start_time"])
    end_t = parse_time(meeting["end_time"])
    first_d = parse_date(meeting["first_date"])
    last_d = parse_date(meeting["last_date"])

    # Compute the actual first occurrence date — the first day on or after
    # first_date that matches one of the meeting's weekdays.
    candidate_starts = [
        first_occurrence(first_d, DAY_CODE_TO_WEEKDAY[d]) for d in days
    ]
    actual_first = min(candidate_starts)
    if actual_first > last_d:
        raise ValueError(
            f"Meeting for {course.get('code')} has no occurrences in range"
        )

    dtstart = datetime.combine(actual_first, start_t, tzinfo=tz)
    dtend = datetime.combine(actual_first, end_t, tzinfo=tz)

    # Per RFC 5545 §3.3.10: when DTSTART has a TZID, RRULE UNTIL MUST be
    # specified as a UTC datetime (Z-suffixed). Convert end-of-day local time
    # to UTC explicitly — the icalendar library does not auto-convert.
    from datetime import timezone as _utc_tz
    until_local = datetime.combine(last_d, time(23, 59, 59), tzinfo=tz)
    until = until_local.astimezone(_utc_tz.utc)

    summary_parts = [course.get("code", ""), course.get("name", "")]
    summary = " — ".join(p for p in summary_parts if p)
    meeting_type = meeting.get("type", "").strip()
    if meeting_type and meeting_type.lower() != "lecture":
        summary = f"{summary} ({meeting_type})"

    event = Event()
    event.add(
        "uid",
        stable_uid(
            course.get("code", ""),
            "meeting",
            meeting_type or "lecture",
            ",".join(days),
            meeting["start_time"],
        ),
    )
    event.add("summary", summary)
    event.add("dtstart", dtstart)
    event.add("dtend", dtend)
    if meeting.get("location"):
        event.add("location", meeting["location"])
    if course.get("instructor"):
        event.add("description", f"Instructor: {course['instructor']}")
    event.add("dtstamp", datetime.now(tz=tz))

    # Recurrence rule.
    event.add(
        "rrule",
        {"freq": "weekly", "byday": days, "until": until},
    )

    # EXDATE entries for any holiday that falls on a meeting day during the
    # term and matches one of this meeting's weekdays.
    exdates = []
    for h_date_str, _title in holidays_by_date.items():
        h_date = parse_date(h_date_str)
        if h_date < actual_first or h_date > last_d:
            continue
        weekday_code = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][h_date.weekday()]
        if weekday_code in days:
            exdates.append(datetime.combine(h_date, start_t, tzinfo=tz))
    if exdates:
        event.add("exdate", exdates)

    add_alarm(
        event,
        reminder_minutes,
        f"Class starting soon: {summary}",
    )
    return event


def build_one_off_event(
    course: dict,
    item: dict,
    tz: ZoneInfo,
    reminder_minutes_by_type: dict,
) -> Event:
    """Build a single VEVENT for an assignment, exam, or quiz."""
    item_type = item["type"]
    title = item["title"]
    item_date = parse_date(item["date"])
    item_time = parse_time(item.get("time", "23:59"))
    duration_min = int(item.get("duration_minutes", 0) or 0)

    dtstart = datetime.combine(item_date, item_time, tzinfo=tz)
    if duration_min > 0:
        dtend = dtstart + timedelta(minutes=duration_min)
    else:
        # 0-duration "due at" event — give it a 15-min visible block so it
        # actually shows up on most calendar UIs, but most clients render
        # zero-duration just fine. We use 0 to keep it semantically correct;
        # add a small block only if explicitly asked.
        dtend = dtstart

    code = course.get("code", "")
    summary = f"{code} — {title}" if code else title

    event = Event()
    event.add(
        "uid",
        stable_uid(code, item_type, title, item["date"], item.get("time", "")),
    )
    event.add("summary", summary)
    event.add("dtstart", dtstart)
    event.add("dtend", dtend)
    if item.get("location"):
        event.add("location", item["location"])
    event.add("dtstamp", datetime.now(tz=tz))

    minutes_before = reminder_minutes_by_type.get(item_type)
    if minutes_before:
        add_alarm(event, minutes_before, f"Upcoming: {summary}")

    return event


def build_holiday_event(holiday: dict, tz: ZoneInfo) -> Event:
    """Build an all-day event for a holiday / no-class day."""
    h_date = parse_date(holiday["date"])
    title = holiday.get("title", "No class")

    event = Event()
    event.add("uid", stable_uid("holiday", holiday["date"], title))
    event.add("summary", title)
    # All-day event: DTSTART is a date (not datetime), DTEND is the next day.
    event.add("dtstart", h_date)
    event.add("dtend", h_date + timedelta(days=1))
    event.add("dtstamp", datetime.now(tz=tz))
    return event


def build_calendar(spec: dict) -> Calendar:
    tz_name = spec.get("timezone", "UTC")
    tz = ZoneInfo(tz_name)

    cal = Calendar()
    cal.add("prodid", "-//syllabus-to-ics//Claude//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", spec.get("calendar_name", "Courses"))
    cal.add("x-wr-timezone", tz_name)

    defaults = spec.get("default_reminders", {}) or {}
    reminder_class = defaults.get("class_meetings_minutes_before")
    reminders_by_type = {
        "assignment": defaults.get("assignments_minutes_before"),
        "quiz": defaults.get("exams_minutes_before"),
        "exam": defaults.get("exams_minutes_before"),
    }

    holidays = spec.get("holidays", []) or []
    holidays_by_date = {h["date"]: h.get("title", "No class") for h in holidays}

    # Holiday events first (visible at the top of an import preview).
    for h in holidays:
        cal.add_component(build_holiday_event(h, tz))

    for course in spec.get("courses", []):
        for meeting in course.get("meetings", []) or []:
            cal.add_component(
                build_meeting_event(
                    course, meeting, tz, holidays_by_date, reminder_class
                )
            )
        for item in course.get("events", []) or []:
            cal.add_component(
                build_one_off_event(course, item, tz, reminders_by_type)
            )

    # Add VTIMEZONE definitions for every TZID referenced in the calendar.
    # Some calendar clients (especially older Outlook versions) require this
    # rather than just trusting the IANA tz name.
    try:
        cal.add_missing_timezones()
    except AttributeError:
        # Older icalendar versions don't have this method; skip silently.
        # Modern clients (Google Calendar, Apple Calendar, Outlook 2016+)
        # accept bare IANA TZIDs without VTIMEZONE blocks.
        pass

    return cal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to JSON spec")
    parser.add_argument("--output", required=True, help="Path for output .ics")
    args = parser.parse_args()

    spec = json.loads(Path(args.input).read_text())
    cal = build_calendar(spec)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(cal.to_ical())

    # Quick sanity summary so the user (and the calling agent) can verify.
    courses = spec.get("courses", [])
    n_meetings = sum(len(c.get("meetings", []) or []) for c in courses)
    n_events = sum(len(c.get("events", []) or []) for c in courses)
    n_holidays = len(spec.get("holidays", []) or [])
    print(
        f"Wrote {out_path} — "
        f"{len(courses)} courses, "
        f"{n_meetings} recurring meetings, "
        f"{n_events} one-off events, "
        f"{n_holidays} holidays."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
