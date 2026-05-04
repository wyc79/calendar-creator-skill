# calendar-creator

An agent skill that turns academic materials — syllabus PDFs, screenshots of your student portal, academic calendar pages — into a single `.ics` calendar file you can import into Google Calendar, Apple Calendar, or Outlook.

It handles the annoying parts: recurring class meetings become proper RRULEs, holidays auto-exclude class dates (so your Monday lecture won't show up on MLK Day), and reminders are configurable per event type.

## What you give it

Any combination of:

- **Syllabus PDFs** — the kind professors hand out the first week
- **Screenshots** of your course schedule from your student portal (WebReg, MyAccess, CalCentral, Banner, whatever your school uses)
- **Academic calendar** — a screenshot, image, or URL of your school's registrar page

You can mix and match. One syllabus is fine. Three syllabi + a portal screenshot + a calendar URL is also fine.

## What you get back

Two files:

1. **`<school>_<term>.ics`** — the calendar file, ready to import
2. **`<school>_<term>.json`** — an editable source-of-truth spec

The JSON is the part most students don't expect but end up loving. If something changes mid-semester (room change, professor adds an assignment, you drop a course), you don't need to re-upload your syllabi. Just send the JSON back to agent with what changed and a fresh `.ics` comes out.

## Example

> **You:** Here's my schedule from Registration, and the academic calendar is at https://www.SchoolName.edu/academic-calendar/. Make me a calendar.
>
> **Agent:**
> *(reads the screenshot, fetches the calendar page)*
>
> **Spring 2026 (Jan 12 – May 1)** · America/Los_Angeles · 15-min reminder before class
>
> | Course | When | Where |
> |---|---|---|
> | CS-123 | Mon 7:00–10:20 PM | Building A-101 |
> | CS-456 | Wed 5:00–7:20 PM | Building B-202 |
> | MTH-101 | Tue/Thu 5:00–5:50 PM | Building C-303 |
>
> Holidays auto-skipped: MLK (1/19), Spring Recess (3/1–10)
>
> Anything wrong, or ship it?
>
> **You:** ship it
>
> **Agent:** *(generates `spring_2026.ics` and `spring_2026.json`)*

## Coming back later

Drop the JSON file back into the agent and tell it what you want changed:

> **You:** *(uploads spring_2026.json)* Move the CS-456 quiz from OFFICE to Building A-101, and switch reminders to 30 minutes before class. Regenerate.

Agents should skip the entire extraction step, apply your edits, and return a fresh `.ics`. No syllabi to dig up again.

## Installation

### Claude

How you install a Claude skill depends on which Claude product you're using. Check Anthropic's skills documentation for the current install method. The general idea:

- **Claude Code:** clone this repo into your skills directory.
  
  ```bash
  git clone https://github.com/<your-username>/calendar-creator.git ~/.claude/skills/calendar-creator
  ```
  
- **Claude.ai:** zip the `calendar-creator/` folder, rename it to `calendar-creator.skill`, and upload it through the skills interface.

After installing, install the Python dependency:

```bash
pip install -r calendar-creator/requirements.txt
```

## What's in this repo

```
.
├── calendar-creator/
│   ├── SKILL.md           ← instructions agents read when the skill triggers
│   └── scripts/
│       └── build_ics.py   ← turns a JSON spec into a valid .ics file
├── requirements.txt
├── LICENSE
└── README.md
```

The split exists for a reason: Agents are good at reading messy syllabi but not great at hand-writing valid iCalendar files (timezone handling, recurrence rules, and escaping have a lot of fiddly RFC 5545 corners). The script handles the iCalendar formatting deterministically — RRULE with proper UTC-suffixed UNTIL, EXDATE entries on recurring meetings for holidays, VALARM blocks, VTIMEZONE, deterministic UIDs (so re-imports update events instead of duplicating them).

## Requirements

- Python 3.9 or newer (uses the standard-library `zoneinfo` module)
- `icalendar` 5.0+

## License

 `MIT LICENSE`

