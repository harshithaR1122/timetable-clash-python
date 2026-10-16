"""Pure timetable and clash rules. No database, no HTTP."""

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat")

_DAY_ALIASES = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
}

# College hours and protected lunch break, in minutes past midnight.
DAY_START = 9 * 60
DAY_END = 17 * 60
LUNCH_START = 13 * 60
LUNCH_END = 14 * 60

MIN_LESSON = 30
MAX_LESSON = 180


class ClashError(ValueError):
    """A timetable entry that must be refused, with a readable reason."""


def parse_hhmm(text):
    """"09:30" -> 570. Accepts "9:30" too; refuses invalid times."""
    s = str(text).strip()

    if ":" not in s:
        raise ClashError("%r is not a time, expected HH:MM" % (text,))

    h, _, m = s.partition(":")

    try:
        h, m = int(h), int(m)
    except ValueError:
        raise ClashError("%r is not a time, expected HH:MM" % (text,))

    if not (0 <= h <= 23) or not (0 <= m <= 59):
        raise ClashError("%r is not a real time of day" % (text,))

    return h * 60 + m


def fmt_hhmm(minutes):
    """570 -> '09:30'."""
    minutes = int(minutes)
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def normalise_day(day):
    """Convert accepted day names and aliases to a standard short name."""
    d = str(day or "").strip().lower()
    d = _DAY_ALIASES.get(d, d)

    if d not in DAYS:
        raise ClashError(
            "%r is not a teaching day (expected one of %s)"
            % (day, ", ".join(DAYS))
        )

    return d


def overlaps(a_start, a_end, b_start, b_end):
    """Return True when two half-open time intervals overlap."""
    return a_start < b_end and b_start < a_end


def overlap_minutes(a_start, a_end, b_start, b_end):
    """Return the number of minutes shared by two intervals."""
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def crosses_lunch(start, end):
    """Check whether a class overlaps the protected lunch break."""
    return overlaps(start, end, LUNCH_START, LUNCH_END)


def within_college_hours(start, end):
    """Check whether a class fits within college hours."""
    return DAY_START <= start and end <= DAY_END


def validate_class(entry):
    """Validate a class and return a cleaned dictionary with times in minutes."""
    day = normalise_day(entry.get("day"))

    start = entry.get("start")
    end = entry.get("end")

    start = start if isinstance(start, int) else parse_hhmm(start)
    end = end if isinstance(end, int) else parse_hhmm(end)

    if end <= start:
        raise ClashError("a class must end after it starts")

    length = end - start

    if length < MIN_LESSON:
        raise ClashError(
            "a class of %d minutes is shorter than the %d minute minimum"
            % (length, MIN_LESSON)
        )

    if length > MAX_LESSON:
        raise ClashError(
            "a class of %d minutes is longer than the %d minute maximum"
            % (length, MAX_LESSON)
        )

    if not within_college_hours(start, end):
        raise ClashError(
            "%s-%s is outside college hours (%s-%s)"
            % (
                fmt_hhmm(start),
                fmt_hhmm(end),
                fmt_hhmm(DAY_START),
                fmt_hhmm(DAY_END),
            )
        )

    if crosses_lunch(start, end):
        raise ClashError(
            "%s-%s runs into the lunch break (%s-%s)"
            % (
                fmt_hhmm(start),
                fmt_hhmm(end),
                fmt_hhmm(LUNCH_START),
                fmt_hhmm(LUNCH_END),
            )
        )

    out = {"day": day, "start": start, "end": end}

    for field in ("teacher", "room", "batch", "subject"):
        value = str(entry.get(field, "")).strip()

        if not value:
            raise ClashError("a class needs a %s" % field)

        out[field] = value

    return out


def find_clashes(candidate, existing, ignore_id=None):
    """Find room, teacher, and batch conflicts with existing classes."""
    out = []

    candidate_day = normalise_day(candidate["day"])

    for other in existing:
        if ignore_id is not None and other.get("id") == ignore_id:
            continue

        # Normalize both day names before comparing them.
        # For example, 'Monday' and 'mon' represent the same day.
        if normalise_day(other["day"]) != candidate_day:
            continue

        if not overlaps(
            candidate["start"],
            candidate["end"],
            other["start"],
            other["end"],
        ):
            continue

        for field, label in (
            ("room", "room"),
            ("teacher", "teacher"),
            ("batch", "batch"),
        ):
            if (
                str(other.get(field, "")).lower()
                == str(candidate.get(field, "")).lower()
            ):
                out.append(
                    {
                        "reason": "%s is already booked" % label,
                        "field": field,
                        "value": candidate[field],
                        "clashes_with": other.get("id"),
                        "subject": other.get("subject"),
                        "day": candidate_day,
                        "window": "%s-%s"
                        % (
                            fmt_hhmm(other["start"]),
                            fmt_hhmm(other["end"]),
                        ),
                        "overlap_minutes": overlap_minutes(
                            candidate["start"],
                            candidate["end"],
                            other["start"],
                            other["end"],
                        ),
                    }
                )

    return out


def build_views(classes, key):
    """Group classes by room, teacher, or batch, sorted by start time."""
    if key not in ("room", "teacher", "batch"):
        raise ClashError(
            "can only build a view by room, teacher or batch"
        )

    view = {}

    for c in classes:
        bucket = view.setdefault(str(c[key]), {d: [] for d in DAYS})

        bucket[normalise_day(c["day"])].append(
            {
                "id": c.get("id"),
                "subject": c.get("subject"),
                "start": fmt_hhmm(c["start"]),
                "end": fmt_hhmm(c["end"]),
                "room": c.get("room"),
                "teacher": c.get("teacher"),
                "batch": c.get("batch"),
            }
        )

    for bucket in view.values():
        for day in bucket:
            bucket[day].sort(key=lambda x: x["start"])

    return view


def free_slots(classes, day, minimum=MIN_LESSON):
    """Find free intervals during college hours, excluding lunch."""
    day = normalise_day(day)

    busy = sorted(
        (c["start"], c["end"])
        for c in classes
        if normalise_day(c["day"]) == day
    )

    busy.append((LUNCH_START, LUNCH_END))
    busy.sort()

    merged = []

    for start, end in busy:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    gaps = []
    cursor = DAY_START

    for start, end in merged:
        if start - cursor >= minimum:
            gaps.append(
                {
                    "start": fmt_hhmm(cursor),
                    "end": fmt_hhmm(start),
                    "minutes": start - cursor,
                }
            )

        cursor = max(cursor, end)

    if DAY_END - cursor >= minimum:
        gaps.append(
            {
                "start": fmt_hhmm(cursor),
                "end": fmt_hhmm(DAY_END),
                "minutes": DAY_END - cursor,
            }
        )

    return gaps


def workload(classes):
    """Calculate total teaching minutes per teacher, highest workload first."""
    out = {}

    for c in classes:
        teacher = str(c["teacher"])
        duration = c["end"] - c["start"]
        out[teacher] = out.get(teacher, 0) + duration

    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))
