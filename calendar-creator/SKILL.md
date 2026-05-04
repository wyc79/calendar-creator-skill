---
name: calendar-creator
description: Convert academic materials — syllabi, course schedules, academic calendar pages — into a single combined .ics calendar file the user can import into Google Calendar, Apple Calendar, or Outlook. Use this skill whenever the user wants to turn a syllabus, course schedule screenshot, screenshot of their student portal, or academic calendar into calendar events. Trigger even when the user doesn't say ".ics" explicitly — phrasings like "make a calendar from my syllabus," "turn this schedule into events," "add my classes and deadlines to my calendar," "I want my whole semester in my calendar," "parse this syllabus into events," or "build me a calendar file from my courses" should all activate this skill. Also trigger when the user uploads a syllabus PDF, course schedule image, or academic calendar URL/screenshot and asks for help organizing their semester. Also trigger when the user uploads a previously-saved courses JSON spec and asks to regenerate, edit, or update their calendar — e.g., "regenerate my calendar from this," "change the room for my Wed class then rebuild the .ics," "add another course to this spec" — the skill knows how to read its own saved spec format and skip the extraction step.
---

# Calendar Creator

Turn academic materials into a single combined `.ics` calendar file, with explicit user confirmation before generating output.

## What goes into the calendar

Four event types — nothing else by default:

- **Recurring class meetings** (lectures, labs, discussions) — encoded as RRULE so they recur properly through the term
- **Assignment & project due dates**
- **Exams & quizzes**
- **Holidays / no-class days** from the academic calendar — both as standalone events AND as EXDATE exclusions on the class meeting recurrences (so a class doesn't show up on a holiday)

Office hours, reading deadlines, and other things are NOT included unless the user specifically asks. Stay focused.

## Inputs the user may give you

Any combination of:

- **Syllabus** — usually PDF, sometimes DOCX, sometimes pasted text
- **Course schedule** — often a screenshot from a student portal (e.g., MyAccess, CalCentral, Banner)
- **Academic calendar** — could be a screenshot, an image, or a URL to a registrar page

If the user gives a URL for the academic calendar, fetch it with `web_fetch`. If it's a PDF or image, read it directly. The user may give one input or several; combine information across all of them.

## Workflow

The whole skill runs in a single conversational loop with one explicit confirmation step before generating the file. Don't generate the `.ics` until the user has confirmed.

### Step 0: Check for a previously-saved spec

If the user uploads a JSON file (or pastes JSON) that has the keys `calendar_name`, `courses`, `holidays`, and `default_reminders`, that's a saved spec from a previous run. Don't redo extraction — the spec already represents user-confirmed events.

Common scenarios:

- **"Regenerate from this"** — they just want a fresh `.ics`. Show the same compact summary as Step 3 so they can spot-check, confirm, then run the script and present both updated files.
- **"Change X in this spec"** — apply the edit to the JSON in memory (e.g., fix a room number, add a course, change reminders), show the changed summary, regenerate.
- **JSON + new materials together** — they're adding to an existing schedule. Read the new materials, merge into the existing spec (append courses, add holidays), show the merged summary, regenerate.

This path skips Steps 1–2 entirely. Jump to Step 3.

### Step 1: Read everything

Read all provided inputs. For PDFs, extract text. For images and screenshots, read them visually (you can see them). For URLs, fetch them. Don't ask the user to retype things you can already see.

If something is genuinely unreadable (corrupt PDF, blurry screenshot), flag it specifically and ask for a re-upload rather than guessing.

### Step 2: Extract events into a structured representation

Build up a single intermediate object covering every course and event found. This is the data you'll feed to `scripts/build_ics.py` after confirmation. The format is:

```json
{
  "calendar_name": "Fall 2025 — My Courses",
  "timezone": "America/Los_Angeles",
  "term_start": "2025-09-22",
  "term_end": "2025-12-05",
  "default_reminders": {
    "class_meetings_minutes_before": 15,
    "assignments_minutes_before": 1440,
    "exams_minutes_before": 10080
  },
  "courses": [
    {
      "code": "CS-101",
      "name": "Introduction to Computer Science",
      "instructor": "Prof. A",
      "meetings": [
        {
          "type": "lecture",
          "days": ["MO", "WE", "FR"],
          "start_time": "10:00",
          "end_time": "10:50",
          "location": "Building A 100",
          "first_date": "2025-09-22",
          "last_date": "2025-12-05"
        },
        {
          "type": "discussion",
          "days": ["TH"],
          "start_time": "14:00",
          "end_time": "15:50",
          "location": "Building A 200",
          "first_date": "2025-09-25",
          "last_date": "2025-12-04"
        }
      ],
      "events": [
        {"type": "assignment", "title": "PS1 due", "date": "2025-10-03", "time": "23:59"},
        {"type": "exam",       "title": "Midterm",  "date": "2025-10-31", "time": "10:00", "duration_minutes": 50, "location": "Building A 100"},
        {"type": "exam",       "title": "Final",    "date": "2025-12-10", "time": "08:00", "duration_minutes": 180}
      ]
    }
  ],
  "holidays": [
    {"date": "2025-11-11", "title": "Veterans Day — no class"},
    {"date": "2025-11-27", "title": "Thanksgiving — no class"},
    {"date": "2025-11-28", "title": "Thanksgiving — no class"}
  ]
}
```

Notes on the format:

- **Days** use iCalendar's two-letter codes: `MO TU WE TH FR SA SU`.
- **Times** are 24-hour `HH:MM`, local to the calendar's timezone.
- **`first_date` and `last_date`** anchor the recurrence — the script generates the RRULE and computes EXDATEs from the holidays automatically.
- **Skip events with missing dates.** If the syllabus says "Final Exam: TBD" or "Quiz date to be announced," do NOT include them with a placeholder. Mention them in the summary so the user knows you saw them but excluded them, and they can add them later.
- **Reminders are global defaults** in the JSON, but the script applies them per event type — class meetings get the `class_meetings_minutes_before` alarm, assignments get the `assignments_minutes_before` alarm, etc. You'll set these defaults based on what the user picks at the confirmation step.

### Step 3: Show a compact summary and get confirmation

This is the most important step. Don't skip it. Don't run the script first and then ask for changes.

**Be brief.** A student looking at this should be able to scan it in under 15 seconds. Use a table for class meetings — much faster to scan than bullet points. Don't preamble ("I've extracted the following…"), don't explain implementation ("auto-excluded from class recurrences"), don't add italicized side-notes that double the length. State things; let the user ask if they want detail.

**Infer the timezone from context.** Most syllabi or registrar pages state the city or region (or it's obvious from the school's name and website). Map that to an IANA timezone — a Los Angeles school → `America/Los_Angeles`, a New York school → `America/New_York`, a Chicago school → `America/Chicago`, a London school → `Europe/London`, and so on. State the assumption in the summary; don't ask. The user will correct it if it's wrong, which costs them one short message instead of forcing a back-and-forth before the summary even appears.

**Roughly this shape — adapt naturally, don't follow rigidly:**

```
**Spring 2026 (Jan 12 – May 1)** · America/Los_Angeles · 15-min reminder before class

| Course | When | Where |
|---|---|---|
| CS-101 Intro to CS (Prof. A) | Mon 7:00–10:20 PM | Building A 210 |
| CS-201 Algorithms (Prof. B) lec | Wed 5:00–7:20 PM | Building A 201 |
| CS-201 disc | Wed 7:30–8:20 PM | Building A 201 |
| CS-201 quiz | Fri 6:00–7:50 PM | Building A 201 |
| MTH-101 Calculus (Prof. C) | Tue/Thu 5:00–5:50 PM | Building B 267 |

Holidays auto-skipped: MLK (1/19), Presidents' Day (2/16), Spring Recess (3/15–22)
Not included (no dates given): final exams, assignments

Anything wrong, or ship it?
```

That's it. One header line carries term + timezone + reminder default. One table for meetings. One line each for holidays and "stuff I left out." One closing line that invites correction.

If the user says "looks good" or similar, generate. If they correct something, apply the change and either regenerate the summary (only if the change was substantial — added a course, changed term dates) or just confirm the fix verbally and proceed (if it's a small tweak — fixing one room number).

**When to be more verbose anyway.** A few cases warrant slightly longer summaries: many courses (8+), genuinely ambiguous data that needs flagging (e.g., conflicting times across sources), or when the user explicitly asks for detail. Default to brief.

**Special case — when this run started from a re-uploaded JSON spec (Step 0 path).** Structure the summary differently. The user already knows what their schedule looks like; what they need to verify is the diff. Lead with what's different, then list what stayed the same so they can confirm nothing got lost.

```
**What's changed:**
- CS-201 quiz: location OFFICE → Building A 201
- All class reminders: 15 min → 30 min before

**Unchanged from your saved schedule:**
- Term: Spring 2026 (Jan 12 – May 1) · America/Los_Angeles
- CS-101 Intro to CS (Prof. A) — Mon 7:00–10:20 PM, Building A 210
- CS-201 Algorithms (Prof. B) lec — Wed 5:00–7:20 PM, Building A 201
- CS-201 disc — Wed 7:30–8:20 PM, Building A 201
- CS-201 quiz time — Fri 6:00–7:50 PM
- MTH-101 Calculus (Prof. C) — Tue/Thu 5:00–5:50 PM, Building B 267
- Holidays: MLK (1/19), Presidents' Day (2/16), Spring Recess (3/15–22)

Apply changes and regenerate?
```

Notes on this format:

- **"What's changed" comes first, always.** Even if the change is tiny ("just changed reminder timing") the user wants to see that line front and center to confirm it landed correctly.
- **Show old → new for modifications**, not just the new value. The user needs to see both sides to verify it matches what they asked for.
- **List additions and removals explicitly** — "Added: PHYS-100 Physics (Prof. D) — Mon/Wed 9:00–10:00 AM, Building C 110" or "Removed: MTH-101".
- **"Unchanged" can be more compact** than the first-time table. Bullets are fine here since the user has already validated this content.
- **If literally nothing changed** (the user said "regenerate as-is"), say so explicitly — "**No changes** from your saved schedule. Regenerate the .ics?" — and skip the unchanged list. They don't need to re-read it.

### Step 4: Generate the `.ics` (and save the spec)

Once the user confirms, save the JSON spec to outputs alongside the `.ics`. The user can keep the JSON as a portable source of truth — edit it later, re-upload it for tweaks, share it with a study group, etc. Both files share a base name so they're obviously paired:

```bash
# Save the spec — same base name as the .ics, side by side in outputs.
cp /tmp/courses.json /mnt/user-data/outputs/<base>.json

# Generate the .ics from that spec.
python3 /path/to/calendar-creator/scripts/build_ics.py \
    --input /mnt/user-data/outputs/<base>.json \
    --output /mnt/user-data/outputs/<base>.ics
```

Pick `<base>` from the user's school + term — e.g., `<school>_spring_2026`, `<school>_fall_2025`. Lowercase, snake_case. If the user's school isn't obvious from context, fall back to `courses_<term>`.

The script handles all the iCalendar formatting — VTIMEZONE, RRULE, EXDATE on class meetings for holidays, VALARM blocks, proper UIDs, escaping. Don't try to write VEVENT blocks by hand; you'll get the timezone or escaping subtly wrong.

### Step 5: Share both files

Use `present_files` with **the `.ics` first, then the `.json`** (the `.ics` is the primary deliverable). Briefly explain what each is and how to use them — keep this to 2–3 lines, not a tutorial:

> The `.ics` is for importing into Google Calendar / Apple Calendar / Outlook. The `.json` is your editable source — re-upload it if you want to change something later, no need to re-process the syllabi.

That's it. Don't write a long postamble.

## Edge cases worth handling well

**Multiple meeting patterns per course.** A course often has lecture on MWF and discussion on a different day. Treat each as a separate `meeting` entry with its own days/times/location.

**Asymmetric end dates.** A Tuesday/Thursday class genuinely has a different last meeting date than an MWF class. Compute `last_date` per meeting based on its days and the term end, rather than using one global last date.

**Late-add courses.** If the user adds a course mid-conversation ("oh I forgot to mention I'm also in PHYS 1A"), don't make them re-upload everything — extract from the new info, append to the courses list, regenerate the summary.

**Conflicting info between sources.** If the syllabus says "lectures Mon/Wed 10am" but the course schedule screenshot says "Mon/Wed/Fri 10am," surface the conflict in the summary and ask which is right rather than silently picking one.

**Time-only events.** Assignment due dates are usually a single moment (e.g., "due 11:59pm"). Treat as a 0-minute event at that time, not a placeholder duration. The script handles this.

**No location given.** That's fine — leave it blank in the JSON, the script will omit the LOCATION field.

**Different academic calendar than university default.** If the user's school is on quarters but the academic calendar PDF they uploaded is for semesters (or vice versa), trust the uploaded materials over assumptions about the school.

## On being conservative

This skill is genuinely useful precisely because students trust the output. If you hallucinate a midterm date or get a recurrence rule wrong, the user misses the exam. So:

- Skip rather than guess
- Surface conflicts rather than resolve them silently
- Show your work in the summary so the user can catch your mistakes before the `.ics` lands in their calendar

The confirmation step exists to catch errors. Use it. Don't be in a rush.
