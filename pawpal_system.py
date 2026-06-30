from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable


Window = tuple[datetime, datetime]

NON_RECURRING_FREQUENCIES = {"", "none", "once", "one-time", "one time"}


def _normalize_frequency(frequency: str) -> str:
    return frequency.strip().lower()


def _add_months(start_date: date, months: int) -> date:
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _validate_window(window: Window) -> None:
    start_time, end_time = window
    if start_time >= end_time:
        raise ValueError("Window start time must be before the end time.")


def _windows_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return first_start < second_end and second_start < first_end


@dataclass
class Task:
    activity_description: str
    time: datetime
    frequency: str
    duration_minutes: int
    due_date: date
    completed: bool = False

    def __post_init__(self) -> None:
        """Validate task details after dataclass initialization."""
        if not self.activity_description.strip():
            raise ValueError("Task activity description cannot be empty.")
        if self.duration_minutes <= 0:
            raise ValueError("Task duration must be greater than 0 minutes.")

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def get_end_time(self) -> datetime:
        """Return the datetime when this task ends."""
        return self.time + timedelta(minutes=self.duration_minutes)

    def calculate_next_due_date(self) -> date:
        """Calculate the next due date based on this task's frequency."""
        frequency = _normalize_frequency(self.frequency)

        if frequency in NON_RECURRING_FREQUENCIES:
            raise ValueError("One-time tasks do not have a next due date.")
        if frequency == "daily":
            return self.due_date + timedelta(days=1)
        if frequency == "weekly":
            return self.due_date + timedelta(weeks=1)
        if frequency == "monthly":
            return _add_months(self.due_date, 1)
        if frequency == "yearly":
            return _add_months(self.due_date, 12)

        raise ValueError(f"Unsupported task frequency: {self.frequency}")


@dataclass
class Pet:
    species: str
    birth_date: date
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a single task to this pet."""
        self.tasks.append(task)

    def add_tasks(self, tasks: Iterable[Task]) -> None:
        """Add multiple tasks to this pet."""
        for task in tasks:
            self.add_task(task)

    def get_tasks(self) -> list[Task]:
        """Return all tasks assigned to this pet."""
        return self.tasks


@dataclass
class Owner:
    name: str
    pets: list[Pet] = field(default_factory=list)
    available_windows: list[Window] = field(default_factory=list)
    unavailable_windows: list[Window] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner."""
        self.pets.append(pet)

    def get_pets(self) -> list[Pet]:
        """Return all pets belonging to this owner."""
        return self.pets

    def get_all_tasks(self) -> list[Task]:
        """Return every task from all of this owner's pets."""
        tasks: list[Task] = []
        for pet in self.pets:
            tasks.extend(pet.get_tasks())
        return tasks

    def get_available_windows(self) -> list[Window]:
        """Return this owner's available scheduling windows."""
        return self.available_windows

    def get_unavailable_windows(self) -> list[Window]:
        """Return this owner's unavailable scheduling windows."""
        return self.unavailable_windows

    def is_available(self, time: datetime, end_time: datetime | None = None) -> bool:
        """Return whether the owner is available for the given time range."""
        end_time = end_time or time

        if time > end_time:
            raise ValueError("Start time cannot be after end time.")

        inside_available_window = not self.available_windows or any(
            start_time <= time and end_time <= window_end
            for start_time, window_end in self.available_windows
        )
        overlaps_unavailable_window = any(
            _windows_overlap(time, end_time, start_time, window_end)
            for start_time, window_end in self.unavailable_windows
        )

        return inside_available_window and not overlaps_unavailable_window

    def add_available_window(self, window: Window) -> None:
        """Add a valid available scheduling window."""
        _validate_window(window)
        self.available_windows.append(window)

    def add_unavailable_window(self, window: Window) -> None:
        """Add a valid unavailable scheduling window."""
        _validate_window(window)
        self.unavailable_windows.append(window)


@dataclass
class Scheduler:
    owner: Owner

    def get_all_tasks(self) -> list[Task]:
        """Return every task available through the scheduler's owner."""
        return self.owner.get_all_tasks()

    def sort_by_time(self) -> list[Task]:
        """Return all tasks sorted by their start time."""
        return sorted(self.get_all_tasks(), key=lambda task: task.time)

    def filter_tasks(self) -> list[Task]:
        """Return incomplete tasks that fit the owner's availability."""
        return [
            task
            for task in self.get_all_tasks()
            if not task.completed
            and self.owner.is_available(task.time, task.get_end_time())
        ]

    def detect_conflicts(self) -> list[Task]:
        """Return tasks whose scheduled time ranges overlap."""
        conflicts: list[Task] = []
        conflict_ids: set[int] = set()
        previous_task: Task | None = None

        for task in self.sort_by_time():
            if previous_task and task.time < previous_task.get_end_time():
                for conflict_task in (previous_task, task):
                    if id(conflict_task) not in conflict_ids:
                        conflicts.append(conflict_task)
                        conflict_ids.add(id(conflict_task))

                if task.get_end_time() > previous_task.get_end_time():
                    previous_task = task
            else:
                previous_task = task

        return conflicts

    def schedule_tasks(self) -> list[Task]:
        """Return a non-overlapping schedule of available incomplete tasks."""
        scheduled_tasks: list[Task] = []

        for task in self.sort_by_time():
            if task.completed:
                continue
            if not self.owner.is_available(task.time, task.get_end_time()):
                continue
            if any(
                _windows_overlap(
                    task.time,
                    task.get_end_time(),
                    scheduled_task.time,
                    scheduled_task.get_end_time(),
                )
                for scheduled_task in scheduled_tasks
            ):
                continue

            scheduled_tasks.append(task)

        return scheduled_tasks

    def mark_task_complete(self, task: Task) -> None:
        """Mark a task complete and create its next occurrence when recurring."""
        task.mark_complete()
        self.create_next_occurrence(task)

    def create_next_occurrence(self, task: Task) -> Task | None:
        """Create and attach the next recurring occurrence for a task."""
        if _normalize_frequency(task.frequency) in NON_RECURRING_FREQUENCIES:
            return None

        next_due_date = task.calculate_next_due_date()
        next_task_time = datetime.combine(next_due_date, task.time.time())
        next_task = Task(
            activity_description=task.activity_description,
            time=next_task_time,
            frequency=task.frequency,
            duration_minutes=task.duration_minutes,
            due_date=next_due_date,
        )

        for pet in self.owner.get_pets():
            if task in pet.get_tasks():
                pet.add_task(next_task)
                break

        return next_task

    def create_next_occurence(self, task: Task) -> Task | None:
        """Call create_next_occurrence using the older misspelled name."""
        return self.create_next_occurrence(task)
