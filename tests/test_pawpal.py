from datetime import date, datetime, time

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task


def _task(description, hour, *, minute=0, duration=30, frequency="daily", priority=0):
    return Task(
        activity_description=description,
        due_date=date(2026, 6, 30),
        start_time=time(hour, minute),
        frequency=frequency,
        duration_minutes=duration,
        priority=priority,
    )


def test_mark_complete_changes_task_status():
    task = _task("Morning walk", 8)

    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_adding_task_to_pet_increases_task_count():
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    task = _task("Feed breakfast", 9, duration=10)

    starting_task_count = len(pet.get_tasks())

    pet.add_task(task)

    assert len(pet.get_tasks()) == starting_task_count + 1
    assert task in pet.get_tasks()


def test_start_datetime_and_end_time_compose_from_split_fields():
    task = _task("Morning walk", 8, duration=30)

    assert task.start_datetime.hour == 8
    assert task.start_datetime.minute == 0
    assert task.get_end_time().hour == 8
    assert task.get_end_time().minute == 30


def test_identical_tasks_on_different_pets_resolve_to_correct_owner():
    owner = Owner(name="Jordan")
    dog = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    cat = Pet(name="Mochi", species="cat", birth_date=date(2022, 9, 3))
    dog_walk = _task("Walk", 8)
    cat_walk = _task("Walk", 8)
    dog.add_task(dog_walk)
    cat.add_task(cat_walk)
    owner.add_pet(dog)
    owner.add_pet(cat)

    assert owner.find_pet_for_task(cat_walk) is cat


def test_owner_json_persistence_round_trips_pets_tasks_and_windows(tmp_path):
    owner = Owner(name="Jordan")
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    task = Task(
        activity_description="Play",
        due_date=date(2026, 6, 30),
        start_time=time(8, 0),
        frequency="daily",
        duration_minutes=20,
        priority=2,
        completed=True,
        flexible=True,
        earliest_start=time(8, 0),
        latest_end=time(10, 0),
        buffer_minutes=5,
        series_start=date(2026, 6, 1),
    )
    pet.add_task(task)
    owner.add_pet(pet)
    owner.add_available_window(
        (datetime(2026, 6, 30, 8, 0), datetime(2026, 6, 30, 12, 0))
    )
    owner.add_unavailable_window(
        (datetime(2026, 6, 30, 9, 0), datetime(2026, 6, 30, 9, 30))
    )

    file_path = tmp_path / "data.json"
    owner.save_to_json(file_path)
    loaded = Owner.load_from_json(file_path)
    loaded_pet = loaded.get_pets()[0]
    loaded_task = loaded_pet.get_tasks()[0]

    assert loaded.name == "Jordan"
    assert loaded_pet.name == "Biscuit"
    assert loaded_pet.species == "dog"
    assert loaded_pet.birth_date == date(2020, 5, 14)
    assert loaded_task.activity_description == "Play"
    assert loaded_task.due_date == date(2026, 6, 30)
    assert loaded_task.start_time == time(8, 0)
    assert loaded_task.frequency == "daily"
    assert loaded_task.duration_minutes == 20
    assert loaded_task.priority == 2
    assert loaded_task.completed is True
    assert loaded_task.flexible is True
    assert loaded_task.earliest_start == time(8, 0)
    assert loaded_task.latest_end == time(10, 0)
    assert loaded_task.buffer_minutes == 5
    assert loaded_task.series_start == date(2026, 6, 1)
    assert loaded.get_available_windows() == [
        (datetime(2026, 6, 30, 8, 0), datetime(2026, 6, 30, 12, 0))
    ]
    assert loaded.get_unavailable_windows() == [
        (datetime(2026, 6, 30, 9, 0), datetime(2026, 6, 30, 9, 30))
    ]
    assert loaded.find_pet_for_task(loaded_task) is loaded_pet


def _single_pet_scheduler(tasks):
    owner = Owner(name="Jordan")
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    pet.add_tasks(tasks)
    owner.add_pet(pet)
    return Scheduler(owner=owner), pet


def test_sort_by_time_orders_out_of_order_tasks():
    evening = _task("Brush", 17, minute=30)
    morning = _task("Walk", 8)
    noon = _task("Feed", 12)
    scheduler, _ = _single_pet_scheduler([evening, morning, noon])

    assert scheduler.sort_by_time() == [morning, noon, evening]


def test_filter_tasks_by_pet_name_is_case_insensitive():
    owner = Owner(name="Jordan")
    dog = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    cat = Pet(name="Mochi", species="cat", birth_date=date(2022, 9, 3))
    dog.add_task(_task("Walk", 8))
    cat.add_task(_task("Feed", 9))
    owner.add_pet(dog)
    owner.add_pet(cat)
    scheduler = Scheduler(owner=owner)

    biscuit_tasks = scheduler.filter_tasks(pet_name="biscuit")

    assert [task.activity_description for task in biscuit_tasks] == ["Walk"]


def test_filter_tasks_by_completion_status():
    done = _task("Walk", 8)
    todo = _task("Feed", 9)
    done.mark_complete()
    scheduler, _ = _single_pet_scheduler([done, todo])

    assert scheduler.filter_tasks(completed=False) == [todo]
    assert scheduler.filter_tasks(completed=True) == [done]


def test_conflict_warnings_flag_overlapping_tasks():
    walk = _task("Walk", 8, duration=60)
    vet = _task("Vet call", 8, minute=30, duration=30)
    clear = _task("Dinner", 18, duration=30)
    scheduler, _ = _single_pet_scheduler([walk, vet, clear])

    warnings = scheduler.conflict_warnings()

    assert len(warnings) == 1
    assert "Walk" in warnings[0]
    assert "Vet call" in warnings[0]


def test_conflict_warnings_empty_when_no_overlap():
    first = _task("Walk", 8, duration=30)
    second = _task("Feed", 9, duration=30)
    scheduler, _ = _single_pet_scheduler([first, second])

    assert scheduler.conflict_warnings() == []


def test_detect_conflicts_flags_overlapping_tasks_only():
    early = _task("Walk", 8, duration=60)
    overlapping = _task("Vet call", 8, minute=30, duration=30)
    clear = _task("Dinner", 18, duration=30)
    scheduler, _ = _single_pet_scheduler([early, overlapping, clear])

    conflicts = scheduler.detect_conflicts()

    assert early in conflicts
    assert overlapping in conflicts
    assert clear not in conflicts


def test_schedule_prefers_higher_priority_on_conflict():
    important = _task("Medication", 10, duration=60, priority=5)
    minor = _task("Brush fur", 10, minute=30, duration=20, priority=1)
    scheduler, _ = _single_pet_scheduler([important, minor])

    scheduled = scheduler.schedule_tasks()

    assert important in scheduled
    assert minor not in scheduled


def test_schedule_keeps_back_to_back_non_overlapping_tasks():
    first = _task("Walk", 8, duration=30)
    second = _task("Feed", 8, minute=30, duration=30)
    scheduler, _ = _single_pet_scheduler([first, second])

    scheduled = scheduler.schedule_tasks()

    assert scheduled == [first, second]


def test_build_plan_reflows_conflict_instead_of_dropping():
    important = _task("Medication", 10, duration=60, priority=5)
    minor = _task("Brush fur", 10, minute=30, duration=20, priority=1)
    scheduler, _ = _single_pet_scheduler([important, minor])

    plan = scheduler.build_plan()

    placed = {entry.task.activity_description for entry in plan.scheduled}
    assert placed == {"Medication", "Brush fur"}  # nothing dropped
    assert plan.unscheduled == []

    moved = [entry for entry in plan.scheduled if entry.moved]
    assert len(moved) == 1
    assert moved[0].task.activity_description == "Brush fur"
    assert moved[0].task.start_datetime >= important.get_end_time()


def test_build_plan_keeps_non_conflicting_tasks_in_place():
    first = _task("Walk", 8, duration=30)
    second = _task("Feed", 8, minute=30, duration=30)
    scheduler, _ = _single_pet_scheduler([first, second])

    plan = scheduler.build_plan()

    assert all(not entry.moved for entry in plan.scheduled)
    assert [entry.task.activity_description for entry in plan.scheduled] == [
        "Walk",
        "Feed",
    ]
    assert plan.unscheduled == []


def test_build_plan_reports_unscheduled_when_no_slot_fits():
    owner = Owner(name="Jordan")
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    keep = _task("Walk", 8, duration=60, priority=5)
    overflow = _task("Vet", 8, duration=60, priority=1)
    pet.add_tasks([keep, overflow])
    owner.add_pet(pet)
    # Only a single 08:00-09:00 slot exists, so one 60-min task cannot fit.
    owner.add_available_window(
        (datetime(2026, 6, 30, 8, 0), datetime(2026, 6, 30, 9, 0))
    )
    scheduler = Scheduler(owner=owner)

    plan = scheduler.build_plan()

    assert {entry.task.activity_description for entry in plan.scheduled} == {"Walk"}
    assert len(plan.unscheduled) == 1
    _, unscheduled_task, reason = plan.unscheduled[0]
    assert unscheduled_task.activity_description == "Vet"
    assert reason  # a human-readable explanation is attached


def test_optimal_strategy_keeps_more_priority_than_greedy():
    owner = Owner(name="Jordan")
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    # Two priority-3 tasks tile 08:00-10:00; one priority-5 task straddles both.
    walk = _task("Walk", 8, duration=60, priority=3)
    training = _task("Training", 9, duration=60, priority=3)
    grooming = _task("Grooming", 8, minute=30, duration=60, priority=5)
    pet.add_tasks([walk, training, grooming])
    owner.add_pet(pet)
    # Only 08:00-10:00 is free, so a dropped task cannot reflow anywhere.
    owner.add_available_window(
        (datetime(2026, 6, 30, 8, 0), datetime(2026, 6, 30, 10, 0))
    )
    scheduler = Scheduler(owner=owner)

    greedy = {e.task.activity_description for e in scheduler.build_plan("greedy").scheduled}
    optimal = {
        e.task.activity_description
        for e in scheduler.build_plan("optimal").scheduled
    }

    assert greedy == {"Grooming"}  # greedy grabs the single priority-5 task
    assert optimal == {"Walk", "Training"}  # optimal keeps the two priority-3 tasks


def _flexible_task(description, *, duration, earliest, latest, priority=0):
    return Task(
        activity_description=description,
        due_date=date(2026, 6, 30),
        start_time=earliest,
        frequency="once",
        duration_minutes=duration,
        priority=priority,
        flexible=True,
        earliest_start=earliest,
        latest_end=latest,
    )


def test_flexible_task_is_auto_placed_in_earliest_free_slot():
    fixed = _task("Walk", 8, duration=60)  # occupies 08:00-09:00
    flex = _flexible_task(
        "Play", duration=30, earliest=time(8, 0), latest=time(12, 0)
    )
    scheduler, _ = _single_pet_scheduler([fixed, flex])

    plan = scheduler.build_plan()

    play = next(e for e in plan.scheduled if e.task.activity_description == "Play")
    assert play.flexible is True
    assert play.moved is False
    # earliest opening in [08:00, 12:00] after the 08:00-09:00 walk is 09:00
    assert play.task.start_datetime == datetime(2026, 6, 30, 9, 0)
    assert plan.unscheduled == []


def test_flexible_task_unscheduled_when_window_is_full():
    fixed = _task("Walk", 8, duration=60)  # fills the whole 08:00-09:00 window
    flex = _flexible_task(
        "Play", duration=60, earliest=time(8, 0), latest=time(9, 0)
    )
    scheduler, _ = _single_pet_scheduler([fixed, flex])

    plan = scheduler.build_plan()

    assert {e.task.activity_description for e in plan.scheduled} == {"Walk"}
    assert [task.activity_description for _, task, _ in plan.unscheduled] == ["Play"]


def test_flexible_task_window_shorter_than_duration_raises():
    with pytest.raises(ValueError):
        _flexible_task(
            "Play", duration=120, earliest=time(8, 0), latest=time(9, 0)
        )


def test_occurrences_between_projects_without_mutating():
    daily = _task("Walk", 8, frequency="daily")
    scheduler, pet = _single_pet_scheduler([daily])

    start = date(2026, 6, 30)
    end = date(2026, 7, 2)
    upcoming = scheduler.occurrences_between(start, end)

    assert [task.due_date for _, task in upcoming] == [
        date(2026, 6, 30),
        date(2026, 7, 1),
        date(2026, 7, 2),
    ]
    assert len(pet.get_tasks()) == 1  # preview must not mutate stored tasks


def test_every_n_days_recurrence():
    task = Task(
        activity_description="Deworm",
        due_date=date(2026, 6, 1),
        start_time=time(9, 0),
        frequency="every 2 days",
        duration_minutes=10,
    )
    scheduler, _ = _single_pet_scheduler([task])

    dates = [t.due_date for _, t in scheduler.occurrences_between(
        date(2026, 6, 1), date(2026, 6, 7)
    )]

    assert dates == [date(2026, 6, 1), date(2026, 6, 3), date(2026, 6, 5), date(2026, 6, 7)]


def test_weekday_recurrence_lands_only_on_named_days():
    task = Task(
        activity_description="Grooming",
        due_date=date(2026, 6, 1),
        start_time=time(9, 0),
        frequency="mon,thu",
        duration_minutes=20,
    )
    scheduler, _ = _single_pet_scheduler([task])

    dates = [t.due_date for _, t in scheduler.occurrences_between(
        date(2026, 6, 1), date(2026, 6, 30)
    )]

    assert dates  # at least one occurrence in June
    assert all(d.weekday() in (0, 3) for d in dates)  # Monday or Thursday only
    assert dates == sorted(dates)


def test_every_hours_recurrence_repeats_within_a_day():
    task = Task(
        activity_description="Meds",
        due_date=date(2026, 6, 30),
        start_time=time(8, 0),
        frequency="every 8 hours",
        duration_minutes=5,
    )
    scheduler, _ = _single_pet_scheduler([task])

    times = [t.start_time for _, t in scheduler.occurrences_between(
        date(2026, 6, 30), date(2026, 6, 30)
    )]

    assert times == [time(8, 0), time(16, 0)]  # 00:00 next day is out of range


def test_occurrences_jump_to_a_far_future_window():
    # A task due decades ago must still project correctly without stepping daily.
    task = Task(
        activity_description="Walk",
        due_date=date(2000, 1, 1),
        start_time=time(8, 0),
        frequency="daily",
        duration_minutes=30,
    )
    scheduler, _ = _single_pet_scheduler([task])

    dates = [t.due_date for _, t in scheduler.occurrences_between(
        date(2026, 6, 29), date(2026, 7, 1)
    )]

    assert dates == [date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1)]


def test_invalid_frequency_is_rejected_at_construction():
    with pytest.raises(ValueError):
        _task("Mystery", 8, frequency="every blue moon")


def test_buffer_pushes_the_next_task_past_the_gap():
    walk = Task(
        activity_description="Walk",
        due_date=date(2026, 6, 30),
        start_time=time(8, 0),
        frequency="once",
        duration_minutes=30,
        priority=5,
        buffer_minutes=15,
    )
    feed = _task("Feed", 8, minute=30, duration=30, priority=1, frequency="once")
    scheduler, _ = _single_pet_scheduler([walk, feed])

    plan = scheduler.build_plan()
    placed = {e.task.activity_description: e for e in plan.scheduled}

    assert placed["Walk"].task.start_datetime == datetime(2026, 6, 30, 8, 0)
    # Feed cannot start until 08:45 (08:30 walk-end + 15-min buffer)
    assert placed["Feed"].task.start_datetime == datetime(2026, 6, 30, 8, 45)
    assert placed["Feed"].moved is True


def test_edf_prefers_the_earlier_deadline_when_only_one_slot_fits():
    owner = Owner(name="Jordan")
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    # relaxed added first, so without EDF insertion order would keep it instead.
    relaxed = _flexible_task(
        "Relaxed", duration=60, earliest=time(8, 0), latest=time(12, 0)
    )
    urgent = _flexible_task(
        "Urgent", duration=60, earliest=time(8, 0), latest=time(9, 0)
    )
    pet.add_tasks([relaxed, urgent])
    owner.add_pet(pet)
    owner.add_available_window(
        (datetime(2026, 6, 30, 8, 0), datetime(2026, 6, 30, 9, 0))
    )
    scheduler = Scheduler(owner=owner)

    plan = scheduler.build_plan()

    assert {e.task.activity_description for e in plan.scheduled} == {"Urgent"}
    assert [t.activity_description for _, t, _ in plan.unscheduled] == ["Relaxed"]


def test_monthly_recurrence_does_not_drift_and_is_window_independent():
    task = Task(
        activity_description="Flea",
        due_date=date(2026, 1, 31),
        start_time=time(9, 0),
        frequency="monthly",
        duration_minutes=15,
    )
    scheduler, _ = _single_pet_scheduler([task])

    def march(window_start):
        return [
            t.due_date
            for _, t in scheduler.occurrences_between(window_start, date(2026, 7, 31))
            if t.due_date.month == 3
        ]

    # Anchored on the 31st, clamped per month; identical no matter where the
    # window starts (no drift to the 28th).
    assert march(date(2026, 1, 1)) == [date(2026, 3, 31)]
    assert march(date(2026, 3, 1)) == [date(2026, 3, 31)]


def test_fixed_task_is_not_reflowed_backward_before_requested_time():
    owner = Owner(name="Jordan")
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    afternoon = _task("Vet at 3pm", 15, duration=30, frequency="once")
    pet.add_task(afternoon)
    owner.add_pet(pet)
    # Owner free only 08:00-09:00; a 3 PM task has no slot at/after 15:00, so it
    # must be left unscheduled, not dragged back to the morning.
    owner.add_available_window(
        (datetime(2026, 6, 30, 8, 0), datetime(2026, 6, 30, 9, 0))
    )
    scheduler = Scheduler(owner=owner)

    plan = scheduler.build_plan()

    assert plan.scheduled == []
    assert [t.activity_description for _, t, _ in plan.unscheduled] == ["Vet at 3pm"]


def test_reflowed_task_can_end_exactly_at_midnight():
    owner = Owner(name="Jordan")
    pet = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    blocker = _task("Blocker", 23, duration=30, priority=5, frequency="once")
    night = _task("Night", 23, duration=30, priority=1, frequency="once")
    pet.add_tasks([blocker, night])
    owner.add_pet(pet)

    plan = Scheduler(owner=owner).build_plan()
    entries = {e.task.activity_description: e for e in plan.scheduled}

    assert set(entries) == {"Blocker", "Night"}
    # Night reflows to 23:30-00:00, ending exactly at midnight.
    assert entries["Night"].task.get_end_time() == datetime(2026, 7, 1, 0, 0)


def test_weighted_interval_selection_respects_buffer():
    # A occupies 08:00-09:00 with a 30-min buffer (reserved through 09:30), so B
    # starting at 09:00 collides once buffers count: only one can be a holder.
    a = Task("A", date(2026, 6, 30), time(8, 0), "once", 60, priority=1, buffer_minutes=30)
    b = Task("B", date(2026, 6, 30), time(9, 0), "once", 60, priority=1)

    selected, _ = Scheduler._weighted_interval_selection([a, b])

    assert len(selected) == 1


def test_monthly_recurrence_clamps_to_end_of_month():
    task = Task(
        activity_description="Flea treatment",
        due_date=date(2026, 1, 31),
        start_time=time(9, 0),
        frequency="monthly",
        duration_minutes=15,
    )

    assert task.calculate_next_due_date() == date(2026, 2, 28)


def test_create_next_occurrence_attaches_to_owning_pet():
    daily = _task("Walk", 8, frequency="daily")
    scheduler, pet = _single_pet_scheduler([daily])

    scheduler.mark_task_complete(daily)

    assert len(pet.get_tasks()) == 2
    assert daily.completed is True
    assert pet.get_tasks()[1].completed is False
