
import pytest

from app.clashes import (
    ClashError,
    build_views,
    crosses_lunch,
    find_clashes,
    free_slots,
    fmt_hhmm,
    normalise_day,
    overlap_minutes,
    overlaps,
    parse_hhmm,
    validate_class,
    workload,
)


def make_class(**overrides):
    entry = {
        "day": "mon",
        "start": "09:00",
        "end": "10:00",
        "teacher": "Teacher A",
        "room": "Room 101",
        "batch": "ISE-A",
        "subject": "Python",
    }
    entry.update(overrides)
    return entry


# Time conversion and day handling

@pytest.mark.parametrize(
    ("value", "expected"),
    [("9:00", 540), ("09:00", 540), ("10:30", 630), ("17:00", 1020)],
)
def test_parse_hhmm_valid(value, expected):
    assert parse_hhmm(value) == expected


@pytest.mark.parametrize("value", ["24:00", "10:60", "lunch", "0900"])
def test_parse_hhmm_invalid(value):
    with pytest.raises(ClashError):
        parse_hhmm(value)


def test_fmt_hhmm():
    assert fmt_hhmm(570) == "09:30"


def test_normalise_day_alias_and_case():
    assert normalise_day("Monday") == "mon"
    assert normalise_day("  TUE  ") == "tue"


def test_normalise_day_invalid():
    with pytest.raises(ClashError):
        normalise_day("Sunday")


# Overlap rules

@pytest.mark.parametrize(
    ("a_start", "a_end", "b_start", "b_end", "expected"),
    [
        (600, 660, 630, 690, True),   # Partial overlap
        (630, 690, 600, 660, True),   # Reverse partial overlap
        (600, 720, 630, 660, True),   # Containment
        (600, 660, 600, 660, True),   # Identical slots
        (600, 660, 660, 720, False),  # Back-to-back boundary
        (600, 630, 660, 690, False),  # Separate slots
    ],
)
def test_overlaps(a_start, a_end, b_start, b_end, expected):
    assert overlaps(a_start, a_end, b_start, b_end) is expected


def test_overlap_minutes():
    assert overlap_minutes(600, 660, 630, 690) == 30
    assert overlap_minutes(600, 630, 630, 660) == 0


# Lunch and class validation

def test_crosses_lunch():
    assert crosses_lunch(750, 810) is True  # 12:30-13:30
    assert crosses_lunch(660, 780) is False  # Ends at 13:00


def test_validate_class_returns_cleaned_entry():
    result = validate_class(make_class(day="Monday"))
    assert result["day"] == "mon"
    assert result["start"] == 540
    assert result["end"] == 600
    assert result["room"] == "Room 101"


@pytest.mark.parametrize(
    "entry",
    [
        make_class(start="10:00", end="10:00"),  # Zero length
        make_class(start="11:00", end="10:00"),  # End before start
        make_class(start="09:00", end="09:15"),  # Too short
        make_class(start="09:00", end="12:30"),  # Too long
        make_class(start="08:30", end="09:30"),  # Before college hours
        make_class(start="12:30", end="13:30"),  # Lunch break
        make_class(day="Sunday"),                # Invalid day
        make_class(room=""),                     # Missing room
    ],
)
def test_validate_class_rejects_invalid_entry(entry):
    with pytest.raises(ClashError):
        validate_class(entry)


# Clash detection

def test_find_clashes_detects_room_teacher_and_batch():
    existing = [
        {
            "id": 1,
            "day": "mon",
            "start": 540,
            "end": 600,
            "teacher": "Teacher A",
            "room": "Room 101",
            "batch": "ISE-A",
            "subject": "Python",
        }
    ]
    candidate = {
        "day": "mon",
        "start": 570,
        "end": 630,
        "teacher": "Teacher A",
        "room": "Room 101",
        "batch": "ISE-A",
        "subject": "Java",
    }

    clashes = find_clashes(candidate, existing)

    assert {item["field"] for item in clashes} == {"room", "teacher", "batch"}
    assert all(item["overlap_minutes"] == 30 for item in clashes)


@pytest.mark.parametrize(
    ("field", "value", "expected_clash"),
    [
        ("room", "Room 101", True),
        ("teacher", "Teacher A", True),
        ("batch", "ISE-A", True),
        ("room", "Room 202", False),
        ("teacher", "Teacher B", False),
        ("batch", "ISE-B", False),
    ],
)
def test_find_clashes_checks_resources(field, value, expected_clash):
    existing = [{
        "id": 1,
        "day": "mon",
        "start": 540,
        "end": 600,
        "teacher": "Teacher A",
        "room": "Room 101",
        "batch": "ISE-A",
        "subject": "Python",
    }]
    candidate = {
        "day": "mon",
        "start": 570,
        "end": 630,
        "teacher": "Teacher B",
        "room": "Room 202",
        "batch": "ISE-B",
        "subject": "Java",
    }
    candidate[field] = value

    clashes = find_clashes(candidate, existing)
    assert bool(clashes) is expected_clash


def test_find_clashes_ignores_other_days_and_back_to_back_classes():
    existing = [{
        "id": 1,
        "day": "tue",
        "start": 540,
        "end": 600,
        "teacher": "Teacher A",
        "room": "Room 101",
        "batch": "ISE-A",
        "subject": "Python",
    }]
    candidate = {
        "day": "mon",
        "start": 600,
        "end": 660,
        "teacher": "Teacher A",
        "room": "Room 101",
        "batch": "ISE-A",
        "subject": "Java",
    }
    assert find_clashes(candidate, existing) == []


def test_find_clashes_can_ignore_an_existing_id():
    existing = [{
        "id": 5,
        "day": "mon",
        "start": 540,
        "end": 600,
        "teacher": "Teacher A",
        "room": "Room 101",
        "batch": "ISE-A",
        "subject": "Python",
    }]
    candidate = {
        "day": "mon",
        "start": 570,
        "end": 630,
        "teacher": "Teacher A",
        "room": "Room 101",
        "batch": "ISE-A",
        "subject": "Java",
    }
    assert find_clashes(candidate, existing, ignore_id=5) == []


# Timetable views, free slots, and workload

def test_build_views_groups_and_sorts_classes():
    classes = [
        {
            "id": 2, "day": "mon", "start": 630, "end": 690,
            "room": "R1", "teacher": "T1", "batch": "B1", "subject": "Java",
        },
        {
            "id": 1, "day": "mon", "start": 540, "end": 600,
            "room": "R1", "teacher": "T1", "batch": "B1", "subject": "Python",
        },
    ]
    view = build_views(classes, "room")
    assert [item["id"] for item in view["R1"]["mon"]] == [1, 2]
    assert len(view["R1"]["tue"]) == 0


def test_build_views_rejects_invalid_key():
    with pytest.raises(ClashError):
        build_views([], "subject")


def test_free_slots_excludes_classes_and_lunch():
    classes = [
        {"day": "mon", "start": 540, "end": 600},
        {"day": "mon", "start": 630, "end": 690},
    ]
    slots = free_slots(classes, "mon")
    assert slots == [
        {"start": "10:00", "end": "10:30", "minutes": 30},
        {"start": "11:30", "end": "13:00", "minutes": 90},
        {"start": "14:00", "end": "17:00", "minutes": 180},
    ]


def test_free_slots_respects_minimum_length():
    classes = [{"day": "mon", "start": 540, "end": 660}]
    slots = free_slots(classes, "mon", minimum=60)
    assert slots == [
        {"start": "11:00", "end": "13:00", "minutes": 120},
        {"start": "14:00", "end": "17:00", "minutes": 180},
    ]


def test_workload_sorts_by_minutes_descending():
    classes = [
        {"teacher": "A", "start": 540, "end": 600},
        {"teacher": "B", "start": 540, "end": 660},
        {"teacher": "A", "start": 600, "end": 630},
    ]
    assert workload(classes) == {"B": 120, "A": 90}
