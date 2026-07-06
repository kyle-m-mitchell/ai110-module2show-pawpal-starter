import os
import re
import sys
from datetime import date, datetime, time, timedelta

from pawpal_system import Owner, Pet, Plan, Scheduler, Task


ANSI_RESET = "\033[0m"
ANSI_STYLES = {
    "bold": "\033[1m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "dim": "\033[2m",
}
ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def supports_color() -> bool:
    """Return whether ANSI color should be used for CLI output."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color_text(text: str, style: str) -> str:
    """Apply an ANSI style when the terminal supports color."""
    if not supports_color():
        return text
    return f"{ANSI_STYLES[style]}{text}{ANSI_RESET}"


def visible_len(text: object) -> int:
    """Return printable length after removing ANSI color codes."""
    return len(ANSI_RE.sub("", str(text)))


def format_table(headers: list[str], rows: list[list[object]]) -> str:
    """Return a simple ASCII table without requiring third-party packages."""
    table_rows = [[str(cell) for cell in row] for row in rows]
    widths = [
        max(visible_len(value) for value in column)
        for column in zip(headers, *table_rows, strict=False)
    ]

    def format_row(row: list[object]) -> str:
        cells = [
            f" {str(value)}{' ' * (width - visible_len(value))} "
            for value, width in zip(row, widths, strict=False)
        ]
        return "|" + "|".join(cells) + "|"

    separator = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    lines = [separator, format_row(headers), separator]
    lines.extend(format_row(row) for row in table_rows)
    lines.append(separator)
    return "\n".join(lines)


def print_section(title: str) -> None:
    """Print a titled CLI section."""
    print(color_text(title, "bold"))
    print(color_text("=" * len(title), "dim"))


def task_icon(task: Task) -> str:
    """Return an emoji that hints at the task's care category."""
    description = task.activity_description.lower()
    if any(word in description for word in ("med", "pill", "deworm", "vaccine")):
        return "💊"
    if any(word in description for word in ("vet", "rabies", "shot")):
        return "🩺"
    if any(word in description for word in ("feed", "breakfast", "dinner", "snack")):
        return "🍽️"
    if any(word in description for word in ("walk", "training")):
        return "🐕"
    if any(word in description for word in ("play", "enrichment")):
        return "🎾"
    if any(word in description for word in ("groom", "brush", "flea")):
        return "🧼"
    return "🐾"


def status_badge(task: Task) -> str:
    """Return a color-coded task status label."""
    if task.completed:
        return color_text("✅ done", "green")
    if task.flexible:
        return color_text("🔵 flexible", "cyan")
    return color_text("🟡 todo", "yellow")


def priority_badge(priority: int) -> str:
    """Return a color-coded priority label."""
    if priority >= 4:
        return color_text(f"high {priority}", "red")
    if priority >= 2:
        return color_text(f"med {priority}", "yellow")
    return color_text(f"low {priority}", "green")


def task_rows(owner: Owner, tasks) -> list[list[object]]:
    """Return formatted rows for task tables."""
    rows: list[list[object]] = []
    for task in tasks:
        pet = owner.find_pet_for_task(task)
        pet_label = pet.name if pet else "Unknown pet"
        time_range = (
            f"{task.start_datetime.strftime('%I:%M %p')} - "
            f"{task.get_end_time().strftime('%I:%M %p')}"
        )
        rows.append(
            [
                time_range,
                pet_label,
                f"{task_icon(task)} {task.activity_description}",
                f"{task.duration_minutes} min",
                priority_badge(task.priority),
                status_badge(task),
            ]
        )
    return rows


def print_tasks(title: str, tasks, owner: Owner) -> None:
    """Print a titled table of tasks with pet, time range, and status."""
    print_section(title)
    if not tasks:
        print("  (none)")
    else:
        print(
            format_table(
                ["Time", "Pet", "Task", "Duration", "Priority", "Status"],
                task_rows(owner, tasks),
            )
        )
    print()


def plan_rows(plan: Plan) -> list[list[object]]:
    """Return formatted rows for a generated plan table."""
    rows: list[list[object]] = []
    for entry in plan.scheduled:
        if entry.flexible:
            note = color_text("auto-scheduled", "cyan")
        elif entry.moved:
            note = color_text(
                f"moved from {entry.requested_start.strftime('%I:%M %p')}", "yellow"
            )
        else:
            note = color_text("kept requested time", "green")
        rows.append(
            [
                entry.task.start_datetime.strftime("%I:%M %p"),
                entry.pet.name,
                f"{task_icon(entry.task)} {entry.task.activity_description}",
                priority_badge(entry.task.priority),
                note,
            ]
        )
    for pet, task, reason in plan.unscheduled:
        rows.append(
            [
                "unscheduled",
                pet.name,
                f"{task_icon(task)} {task.activity_description}",
                priority_badge(task.priority),
                color_text(reason, "red"),
            ]
        )
    return rows


def print_plan(title: str, plan: Plan) -> None:
    """Print a generated plan as a table."""
    print_section(title)
    print(format_table(["Start", "Pet", "Task", "Priority", "Result"], plan_rows(plan)))
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
    print_section("Schedule check")
    warnings = scheduler.conflict_warnings()
    if warnings:
        for warning in warnings:
            print(f"  {color_text(warning, 'red')}")
    else:
        print(f"  {color_text('✅ No conflicts.', 'green')}")
    print()

    # 4) SUGGESTED PLAN -- conflicts are reflowed to a free slot, not dropped.
    plan = scheduler.build_plan()
    print_plan("Suggested plan (higher priority wins, nothing dropped)", plan)

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

    print_section("Greedy vs. Optimal (only 08:00-10:00 free)")
    for strategy in ("greedy", "optimal"):
        plan = scheduler.build_plan(strategy=strategy)
        print(color_text(f"{strategy.title()}:", "bold"))
        print(
            format_table(
                ["Start", "Pet", "Task", "Priority", "Result"], plan_rows(plan)
            )
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

    print_section("Upcoming occurrences (next 2 days) — richer recurrence grammar")
    upcoming = Scheduler(owner=owner).occurrences_between(day, day + timedelta(days=2))
    print(
        format_table(
            ["When", "Pet", "Task", "Frequency"],
            [
                [
                    task.start_datetime.strftime("%a %m-%d %I:%M %p"),
                    pet.name,
                    f"{task_icon(task)} {task.activity_description}",
                    task.frequency,
                ]
                for pet, task in upcoming
            ],
        )
    )
    print()

    print_section("Buffer keeps tasks from stacking")
    other = Owner(name="Sam")
    cat = Pet(name="Mochi", species="cat", birth_date=date(2022, 9, 3))
    other.add_pet(cat)
    cat.add_tasks(
        [
            Task(
                "Vet visit",
                day,
                time(10, 0),
                "once",
                30,
                priority=5,
                buffer_minutes=20,
            ),
            Task("Feed", day, time(10, 30), "once", 15, priority=1),
        ]
    )
    print_plan("Buffered plan", Scheduler(owner=other).build_plan())


if __name__ == "__main__":
    main()
    compare_strategies()
    demo_recurrence_and_buffer()
