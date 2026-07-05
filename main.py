from datetime import date, datetime, time, timedelta

from pawpal_system import Owner, Pet, Scheduler, Task


def print_tasks(title: str, tasks, owner: Owner) -> None:
    """Print a titled block of tasks with pet, time range, and status."""
    print(title)
    print("-" * len(title))
    if not tasks:
        print("  (none)")
    for task in tasks:
        pet = owner.find_pet_for_task(task)
        pet_label = pet.name if pet else "Unknown pet"
        start = task.start_datetime.strftime("%I:%M %p")
        end = task.get_end_time().strftime("%I:%M %p")
        status = "done" if task.completed else "todo"
        print(
            f"  {start}-{end}: {task.activity_description} "
            f"for {pet_label} ({task.duration_minutes} min) [{status}]"
        )
    print()


def main() -> None:
    today = date.today()

    owner = Owner(name="Jordan")
    dog = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    cat = Pet(name="Mochi", species="cat", birth_date=date(2022, 9, 3))
    owner.add_pet(dog)
    owner.add_pet(cat)

    # Tasks are added OUT OF ORDER on purpose so sorting has something to do.
    grooming = Task("Brush fur", today, time(17, 30), "weekly", 20)
    morning_walk = Task("Morning walk", today, time(8, 0), "daily", 30)
    cat_breakfast = Task("Feed breakfast", today, time(9, 0), "daily", 10)
    # This vet call overlaps the morning walk (08:15 falls inside 08:00-08:30).
    vet_call = Task("Vet call", today, time(8, 15), "once", 20, priority=5)
    # A flexible task: PawPal picks any 45-min slot between noon and 5 PM.
    playtime = Task(
        "Playtime",
        today,
        time(12, 0),
        "daily",
        45,
        flexible=True,
        earliest_start=time(12, 0),
        latest_end=time(17, 0),
    )

    dog.add_tasks([grooming, morning_walk, vet_call, playtime])
    cat.add_task(cat_breakfast)

    scheduler = Scheduler(owner=owner)

    # 1) SORTING BY TIME -- sort_by_time() sorts by start_datetime under the hood.
    print_tasks("All tasks, sorted by time", scheduler.sort_by_time(), owner)

    # A lambda key sorts the same tasks by their "HH:MM" start string. "%H:%M"
    # is zero-padded 24-hour, so lexical string order == chronological order.
    by_hhmm = sorted(
        scheduler.get_all_tasks(),
        key=lambda task: task.start_time.strftime("%H:%M"),
    )
    print_tasks("Same tasks, sorted by HH:MM string (lambda key)", by_hhmm, owner)

    # 2) FILTERING by pet name (case-insensitive) and by completion status.
    print_tasks(
        "Biscuit's tasks (filter by pet name)",
        scheduler.filter_tasks(pet_name="biscuit"),
        owner,
    )

    # 3) CONFLICT DETECTION -- lightweight warnings, never crashes.
    print("Schedule check")
    print("--------------")
    warnings = scheduler.conflict_warnings()
    if warnings:
        for warning in warnings:
            print(f"  {warning}")
    else:
        print("  No conflicts. 🎉")
    print()

    # 4) SUGGESTED PLAN -- conflicts are reflowed to a free slot, not dropped.
    print("Suggested plan (higher priority wins, nothing dropped)")
    print("------------------------------------------------------")
    plan = scheduler.build_plan()
    for line in plan.explain():
        print(f"  {line}")
    print()

    # 5) RECURRING TASKS -- completing a daily task auto-creates tomorrow's copy.
    before = len(dog.get_tasks())
    scheduler.mark_task_complete(morning_walk)
    next_walk = dog.get_tasks()[-1]
    print(
        f"Completed '{morning_walk.activity_description}': Biscuit went from "
        f"{before} to {len(dog.get_tasks())} tasks; the next one is due "
        f"{next_walk.due_date} (today + 1 day via timedelta).\n"
    )

    # 6) FILTERING by completion status.
    print_tasks(
        "Remaining to-do tasks (filter by completion status)",
        scheduler.filter_tasks(completed=False),
        owner,
    )


def compare_strategies() -> None:
    """Contrast greedy vs. optimal packing on a tight, conflict-heavy morning.

    The owner is only free 08:00-10:00, so nothing can reflow outside it and the
    scheduler must *drop* a task -- which makes the choice of which to keep matter.
    """
    day = date.today()
    owner = Owner(name="Jordan")
    dog = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    owner.add_pet(dog)
    owner.add_available_window(
        (datetime.combine(day, time(8, 0)), datetime.combine(day, time(10, 0)))
    )
    dog.add_tasks(
        [
            Task("Walk", day, time(8, 0), "once", 60, priority=3),
            Task("Training", day, time(9, 0), "once", 60, priority=3),
            Task("Grooming", day, time(8, 30), "once", 60, priority=5),
        ]
    )
    scheduler = Scheduler(owner=owner)

    print("Greedy vs. Optimal (only 08:00-10:00 free)")
    print("==========================================")
    for strategy in ("greedy", "optimal"):
        plan = scheduler.build_plan(strategy=strategy)
        print(f"{strategy.title()}:")
        for entry in plan.scheduled:
            when = entry.task.start_datetime.strftime("%I:%M %p")
            print(
                f"  {when}  {entry.task.activity_description} "
                f"(priority {entry.task.priority})"
            )
        for _, task, reason in plan.unscheduled:
            print(
                f"  ⚠️  Skipped {task.activity_description} "
                f"(priority {task.priority}) — {reason}"
            )
        print()


def demo_recurrence_and_buffer() -> None:
    """Show the richer recurrence grammar (Tier 3) and buffer gaps (Tier 4)."""
    day = date.today()

    owner = Owner(name="Jordan")
    dog = Pet(name="Biscuit", species="dog", birth_date=date(2020, 5, 14))
    owner.add_pet(dog)
    dog.add_tasks(
        [
            Task("Meds", day, time(6, 0), "every 8 hours", 5),
            Task("Grooming", day, time(9, 0), "mon,thu", 30),
            Task("Deworm", day, time(9, 0), "every 2 days", 10),
        ]
    )

    print("Upcoming occurrences (next 2 days) — richer recurrence grammar")
    print("==============================================================")
    upcoming = Scheduler(owner=owner).occurrences_between(day, day + timedelta(days=2))
    for _, task in upcoming:
        when = task.start_datetime.strftime("%a %m-%d %I:%M %p")
        print(f"  {when}  {task.activity_description} ({task.frequency})")
    print()

    print("Buffer keeps tasks from stacking")
    print("================================")
    other = Owner(name="Sam")
    cat = Pet(name="Mochi", species="cat", birth_date=date(2022, 9, 3))
    other.add_pet(cat)
    cat.add_tasks(
        [
            Task("Vet visit", day, time(10, 0), "once", 30, priority=5, buffer_minutes=20),
            Task("Feed", day, time(10, 30), "once", 15, priority=1),
        ]
    )
    for line in Scheduler(owner=other).build_plan().explain():
        print(f"  {line}")
    print()


if __name__ == "__main__":
    main()
    compare_strategies()
    demo_recurrence_and_buffer()
