"""Edge-case tests for the PawPal scheduler.

Covers the three requested behaviours (sorting correctness, daily-recurrence
follow-up, duplicate-time conflict detection) plus the subtler cases that the
sorting / recurrence / conflict / availability logic is most likely to get
wrong. Shared task/scheduler helpers are reused from ``test_pawpal``.
"""

from datetime import date, datetime, time

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task, parse_recurrence
from test_pawpal import _single_pet_scheduler, _task


def _dated_task(description, due, hour, *, minute=0, duration=30, frequency="once"):
    """A task on an explicit date (the shared helper pins one fixed date)."""
    return Task(
        activity_description=description,
        due_date=due,
        start_time=time(hour, minute),
        frequency=frequency,
        duration_minutes=duration,
    )


# --------------------------------------------------------------------------- #
# Requested: sorting correctness                                              #
# --------------------------------------------------------------------------- #

def test_sort_by_time_is_chronological_across_pets_and_dates():
    owner = Owner(name="Jordan")
    dog = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    cat = Pet(name="Mochi", species="cat", birth_date=date(2022, 9, 3))
    # Deliberately added out of order and split across two pets and two days.
    tomorrow_early = _dated_task("Tomorrow walk", date(2026, 7, 1), 7)
    today_late = _dated_task("Today dinner", date(2026, 6, 30), 18)
    today_early = _dated_task("Today breakfast", date(2026, 6, 30), 8)
    dog.add_tasks([tomorrow_early, today_late])
    cat.add_task(today_early)
    owner.add_pet(dog)
    owner.add_pet(cat)
    scheduler = Scheduler(owner=owner)

    ordered = scheduler.sort_by_time()

    assert ordered == [today_early, today_late, tomorrow_early]
    # Every start is <= the next one: the defining property of chronological order.
    starts = [t.start_datetime for t in ordered]
    assert starts == sorted(starts)


def test_sort_by_time_tiebreaks_same_start_by_end_then_description():
    # Same start time: the shorter task (earlier end) comes first; when start and
    # end match too, the tiebreak falls through to the description alphabetically.
    longer = _task("Aardvark long", 9, duration=60)
    shorter = _task("Zebra short", 9, duration=30)
    same_a = _task("Apple", 9, duration=30)
    same_z = _task("Banana", 9, duration=30)
    scheduler, _ = _single_pet_scheduler([longer, shorter, same_a, same_z])

    ordered = scheduler.sort_by_time()

    # Three 30-min tasks (end 09:30) precede the 60-min one (end 10:00);
    # among the 30-min tasks, alphabetical by description.
    assert ordered == [same_a, same_z, shorter, longer]


# --------------------------------------------------------------------------- #
# Requested: recurrence — daily complete creates the following day's task     #
# --------------------------------------------------------------------------- #

def test_completing_daily_task_creates_task_for_the_following_day():
    walk = _task("Morning walk", 8, frequency="daily")  # due 2026-06-30
    scheduler, pet = _single_pet_scheduler([walk])

    scheduler.mark_task_complete(walk)

    assert walk.completed is True
    assert len(pet.get_tasks()) == 2
    follow_up = pet.get_tasks()[1]
    assert follow_up.due_date == date(2026, 7, 1)      # the very next day
    assert follow_up.start_time == time(8, 0)          # same time of day
    assert follow_up.frequency == "daily"              # rule carries forward
    assert follow_up.completed is False                # fresh, not done


def test_completing_one_time_task_creates_no_follow_up():
    once = _task("Vet visit", 10, frequency="once")
    scheduler, pet = _single_pet_scheduler([once])

    scheduler.mark_task_complete(once)

    assert len(pet.get_tasks()) == 1  # nothing added for a non-recurring task


# --------------------------------------------------------------------------- #
# Requested: conflict detection flags duplicate / identical times             #
# --------------------------------------------------------------------------- #

def test_detect_conflicts_flags_two_tasks_at_the_identical_time():
    feed = _task("Feed", 8, duration=30)
    meds = _task("Meds", 8, duration=30)  # exact same 08:00-08:30 slot
    scheduler, _ = _single_pet_scheduler([feed, meds])

    conflicts = scheduler.detect_conflicts()

    assert feed in conflicts
    assert meds in conflicts
    assert len(scheduler.find_conflicts()) == 1  # exactly one overlapping pair


# --------------------------------------------------------------------------- #
# Conflict detection: the tricky sweep cases                                  #
# --------------------------------------------------------------------------- #

def test_conflicts_found_for_long_task_overlapping_two_disjoint_short_ones():
    # A spans the whole morning; B and C sit inside it but do NOT touch each
    # other. A naive sweep that forgets the max end would miss C.
    long_task = _task("Daycare", 9, duration=180)         # 09:00-12:00
    early = _task("Pill", 9, minute=30, duration=15)      # 09:30-09:45
    late = _task("Snack", 11, duration=15)                # 11:00-11:15
    scheduler, _ = _single_pet_scheduler([long_task, early, late])

    conflicts = scheduler.detect_conflicts()

    assert set(conflicts) == {long_task, early, late}
    # find_conflicts sees A-B and A-C, but not B-C (they are disjoint).
    pairs = {frozenset(p) for p in scheduler.find_conflicts()}
    assert pairs == {frozenset({long_task, early}), frozenset({long_task, late})}


def test_back_to_back_tasks_that_only_touch_are_not_conflicts():
    first = _task("Walk", 10, duration=30)              # 10:00-10:30
    second = _task("Feed", 10, minute=30, duration=30)  # 10:30-11:00 (touches)
    scheduler, _ = _single_pet_scheduler([first, second])

    assert scheduler.detect_conflicts() == []
    assert scheduler.find_conflicts() == []


def test_detect_conflicts_and_find_conflicts_agree_on_the_conflicting_set():
    a = _task("A", 9, duration=90)                 # 09:00-10:30
    b = _task("B", 10, duration=30)                # 10:00-10:30 (overlaps A)
    c = _task("C", 14, duration=30)               # 14:00-14:30 (clear)
    scheduler, _ = _single_pet_scheduler([a, b, c])

    swept = set(scheduler.detect_conflicts())
    paired = {task for pair in scheduler.find_conflicts() for task in pair}

    assert swept == paired == {a, b}


# --------------------------------------------------------------------------- #
# Recurrence: month-end anchoring and its known drift bug                     #
# --------------------------------------------------------------------------- #

def test_yearly_recurrence_recovers_leap_day_after_non_leap_years():
    # Feb 29 2028 (leap). Non-leap years clamp to Feb 28, but because the preview
    # is anchored on the base day-of-month it must recover Feb 29 in 2032.
    vaccine = _dated_task("Rabies shot", date(2028, 2, 29), 9, frequency="yearly")
    scheduler, _ = _single_pet_scheduler([vaccine])

    dates = [
        t.due_date
        for _, t in scheduler.occurrences_between(date(2028, 1, 1), date(2032, 12, 31))
    ]

    assert dates == [
        date(2028, 2, 29),
        date(2029, 2, 28),
        date(2030, 2, 28),
        date(2031, 2, 28),
        date(2032, 2, 29),  # leap day recovered, not stuck on the 28th
    ]


def test_completion_chain_matches_anchored_preview_for_month_end_task():
    # Regression: the "mark complete -> next occurrence" chain used to step via
    # Recurrence.next_after() and re-anchor on the clamped Feb 28 (drifting to
    # Mar 28), disagreeing with the anchored preview. Both paths now stay pinned
    # to the original day-of-month.
    monthly = _dated_task("Flea treatment", date(2026, 1, 31), 9, frequency="monthly")
    scheduler, pet = _single_pet_scheduler([monthly])

    # The anchored preview is the source of truth.
    preview = [
        t.due_date
        for _, t in scheduler.occurrences_between(date(2026, 1, 1), date(2026, 4, 30))
    ]

    # Walk the "mark complete -> next occurrence" chain the same number of steps.
    chain = [monthly.due_date]
    current = monthly
    while len(chain) < len(preview):
        scheduler.mark_task_complete(current)
        current = pet.get_tasks()[-1]
        chain.append(current.due_date)

    assert chain == preview  # both hold Jan 31 -> Feb 28 -> Mar 31 -> Apr 30


# --------------------------------------------------------------------------- #
# Recurrence: weekday resolution                                              #
# --------------------------------------------------------------------------- #

def test_weekday_recurrence_includes_the_start_day_itself():
    # 2026-06-01 is a Monday; a "mon" rule whose window opens that same day must
    # include June 1, not skip a week ahead.
    groom = _dated_task("Grooming", date(2026, 6, 1), 15, frequency="mon")
    scheduler, _ = _single_pet_scheduler([groom])

    dates = [
        t.due_date
        for _, t in scheduler.occurrences_between(date(2026, 6, 1), date(2026, 6, 8))
    ]

    assert dates == [date(2026, 6, 1), date(2026, 6, 8)]


# --------------------------------------------------------------------------- #
# Frequency parsing                                                           #
# --------------------------------------------------------------------------- #

def test_every_zero_interval_is_rejected():
    with pytest.raises(ValueError):
        parse_recurrence("every 0 days")


def test_every_day_is_equivalent_to_every_1_day():
    assert parse_recurrence("every day") == parse_recurrence("every 1 day")


def test_weekday_parsing_ignores_case_and_extra_whitespace():
    spaced = parse_recurrence("  MON ,   weds  ,friday ")
    assert spaced.kind == "weekdays"
    assert spaced.weekdays == (0, 2, 4)  # deduped and sorted Mon/Wed/Fri


def test_mixing_a_valid_weekday_with_garbage_is_rejected():
    with pytest.raises(ValueError):
        parse_recurrence("mon and someday")


# --------------------------------------------------------------------------- #
# Availability windows                                                        #
# --------------------------------------------------------------------------- #

def test_owner_with_no_windows_is_available_all_day():
    owner = Owner(name="Jordan")  # no available/unavailable windows configured

    assert owner.is_available(
        datetime(2026, 6, 30, 3, 0), datetime(2026, 6, 30, 23, 30)
    )


def test_task_touching_the_edge_of_an_unavailable_window_is_allowed():
    owner = Owner(name="Jordan")
    owner.add_unavailable_window(
        (datetime(2026, 6, 30, 10, 0), datetime(2026, 6, 30, 11, 0))
    )

    # Ends exactly when the block starts -> touching, not overlapping.
    assert owner.is_available(
        datetime(2026, 6, 30, 9, 0), datetime(2026, 6, 30, 10, 0)
    )
    # Starts one minute inside the block -> not available.
    assert not owner.is_available(
        datetime(2026, 6, 30, 10, 30), datetime(2026, 6, 30, 10, 45)
    )


def test_is_available_rejects_a_backwards_time_range():
    owner = Owner(name="Jordan")
    with pytest.raises(ValueError):
        owner.is_available(
            datetime(2026, 6, 30, 11, 0), datetime(2026, 6, 30, 10, 0)
        )


# --------------------------------------------------------------------------- #
# Task validation                                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "kwargs",
    [
        {"activity_description": "   "},          # blank description
        {"duration_minutes": 0},                  # zero duration
        {"duration_minutes": -5},                 # negative duration
        {"buffer_minutes": -1},                   # negative buffer
    ],
)
def test_invalid_task_fields_are_rejected_at_construction(kwargs):
    base = dict(
        activity_description="Walk",
        due_date=date(2026, 6, 30),
        start_time=time(8, 0),
        frequency="once",
        duration_minutes=30,
    )
    base.update(kwargs)
    with pytest.raises(ValueError):
        Task(**base)


def test_flexible_task_with_inverted_window_is_rejected():
    with pytest.raises(ValueError):
        Task(
            activity_description="Play",
            due_date=date(2026, 6, 30),
            start_time=time(10, 0),
            frequency="once",
            duration_minutes=30,
            flexible=True,
            earliest_start=time(11, 0),  # earliest after latest
            latest_end=time(10, 0),
        )
