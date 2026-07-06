from __future__ import annotations

import json
import re
from bisect import bisect_right
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable


Window = tuple[datetime, datetime]

NON_RECURRING_FREQUENCIES = {"", "none", "once", "one-time", "one time"}

# Every accepted spelling of a weekday -> its Python weekday index (Mon=0).
WEEKDAY_INDEX = {
    name: index
    for index, names in enumerate(
        [
            ("mon", "monday"),
            ("tue", "tues", "tuesday"),
            ("wed", "weds", "wednesday"),
            ("thu", "thur", "thurs", "thursday"),
            ("fri", "friday"),
            ("sat", "saturday"),
            ("sun", "sunday"),
        ]
    )
    for name in names
}

_EVERY_N = re.compile(r"every\s+(\d+)\s+(day|days|week|weeks|hour|hours)")
_EVERY_ONE = re.compile(r"every\s+(day|week|hour)")


def _normalize_frequency(frequency: str) -> str:
    """Lower-case and trim a frequency string for parsing/comparison."""
    return frequency.strip().lower()


def _add_months(start_date: date, months: int) -> date:
    """Add ``months`` to a date, clamping the day to the target month's length.

    Jan 31 + 1 month -> Feb 28 (or 29). The day is always derived from the
    *original* ``start_date.day``, so callers that want a stable day-of-month
    anchor should pass the original base date, not a previously clamped result.
    """
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class Recurrence:
    """A parsed repeat rule that can project occurrences without stepping one
    period at a time.

    ``kind`` is one of: ``once``, ``daily``, ``weekly``, ``monthly``,
    ``yearly``, ``every_days``, ``every_weeks``, ``every_hours`` (``interval``
    periods apart), or ``weekdays`` (repeats on the named ``weekdays`` each week).
    """

    kind: str
    interval: int = 1
    weekdays: tuple[int, ...] = ()

    @property
    def is_recurring(self) -> bool:
        """Return whether this rule repeats (everything except ``once``)."""
        return self.kind != "once"

    def _step(self) -> timedelta | None:
        """Return the fixed timedelta between occurrences, if the rule has one."""
        if self.kind == "daily":
            return timedelta(days=1)
        if self.kind == "weekly":
            return timedelta(weeks=1)
        if self.kind == "every_days":
            return timedelta(days=self.interval)
        if self.kind == "every_weeks":
            return timedelta(weeks=self.interval)
        if self.kind == "every_hours":
            return timedelta(hours=self.interval)
        return None

    def next_after(self, moment: datetime, anchor: date | None = None) -> datetime:
        """Return the next occurrence strictly after a given occurrence.

        For monthly/yearly rules, pass ``anchor`` (the series' original start
        date) so the result stays pinned to the original day-of-month. Stepping
        without it re-anchors on a clamped date (Jan 31 -> Feb 28 -> Mar 28) and
        permanently loses the 31st; anchoring recovers it (... -> Mar 31). Other
        cadences never drift, so ``anchor`` is ignored for them.
        """
        step = self._step()
        if step is not None:
            return moment + step
        if self.kind in ("monthly", "yearly"):
            months = 1 if self.kind == "monthly" else 12
            anchor = anchor or moment.date()
            # Month index is linear in the step count even when the day is
            # clamped, so recover this occurrence's index and take the next one.
            index = (
                (moment.year - anchor.year) * 12 + moment.month - anchor.month
            ) // months
            return datetime.combine(
                _add_months(anchor, (index + 1) * months), moment.time()
            )
        if self.kind == "weekdays":
            day = moment.date() + timedelta(days=1)
            while day.weekday() not in self.weekdays:
                day += timedelta(days=1)
            return datetime.combine(day, moment.time())
        raise ValueError("One-time tasks do not have a next occurrence.")

    def _first_on_or_after(self, base: datetime, target: datetime) -> datetime:
        """Jump straight to the first occurrence >= ``target`` (no per-period loop)."""
        if self.kind == "weekdays":
            moment = max(base, target)
            day = moment.date()
            for _ in range(8):
                candidate = datetime.combine(day, base.time())
                if day.weekday() in self.weekdays and candidate >= moment:
                    return candidate
                day += timedelta(days=1)
            raise ValueError("Weekday recurrence has no valid days.")

        if target <= base:
            return base

        step = self._step()
        if step is not None:
            skips = (target - base) // step
            first = base + skips * step
            if first < target:
                first += step
            return first

        if self.kind in ("monthly", "yearly"):
            months = 1 if self.kind == "monthly" else 12
            base_date, base_time = base.date(), base.time()
            guess = max(
                ((target.year - base_date.year) * 12 + target.month - base_date.month)
                // months,
                0,
            )
            candidate = datetime.combine(
                _add_months(base_date, guess * months), base_time
            )
            while candidate > target and guess > 0:
                guess -= 1
                candidate = datetime.combine(
                    _add_months(base_date, guess * months), base_time
                )
            while candidate < target:
                guess += 1
                candidate = datetime.combine(
                    _add_months(base_date, guess * months), base_time
                )
            return candidate

        raise ValueError("One-time tasks do not repeat.")

    def occurrences_in(
        self, base: datetime, window_start: datetime, window_end: datetime
    ) -> list[datetime]:
        """Return every occurrence datetime within [window_start, window_end].

        Jumps to the first occurrence in range first, so a task whose base date
        is far in the past costs O(1) to reach the window instead of O(periods).
        Monthly/yearly rules are generated *anchored on the base day-of-month*
        (see ``_month_anchored_occurrences``) rather than by stepping, so the
        result never depends on where the window starts.
        """
        if self.kind == "once":
            return [base] if window_start <= base <= window_end else []
        if self.kind in ("monthly", "yearly"):
            return self._month_anchored_occurrences(base, window_start, window_end)

        occurrences: list[datetime] = []
        moment = self._first_on_or_after(base, window_start)
        while moment <= window_end:
            occurrences.append(moment)
            moment = self.next_after(moment)
        return occurrences

    def _month_anchored_occurrences(
        self, base: datetime, window_start: datetime, window_end: datetime
    ) -> list[datetime]:
        """Generate monthly/yearly occurrences anchored on the base day-of-month.

        Each occurrence is ``_add_months(base_date, k * months)`` for increasing
        k, so a clamp in a short month (Jan 31 -> Feb 28) never drifts the later
        months -- they stay Mar 31, Apr 30, ... . Stepping with ``next_after``
        instead would re-anchor on the clamped date and permanently lose the
        31st, and would also make the result depend on the window start.
        """
        months = 1 if self.kind == "monthly" else 12
        base_date, base_time = base.date(), base.time()

        # First in-range occurrence is anchored + O(1); recover its k exactly
        # (the month index is linear in k even though the day may be clamped).
        first = self._first_on_or_after(base, window_start)
        index = (
            (first.year - base_date.year) * 12 + first.month - base_date.month
        ) // months

        occurrences: list[datetime] = []
        moment = first
        while moment <= window_end:
            occurrences.append(moment)
            index += 1
            moment = datetime.combine(
                _add_months(base_date, index * months), base_time
            )
        return occurrences


def parse_recurrence(frequency: str) -> Recurrence:
    """Parse a frequency string into a :class:`Recurrence` (raises on garbage)."""
    normalized = _normalize_frequency(frequency)

    if normalized in NON_RECURRING_FREQUENCIES:
        return Recurrence("once")
    if normalized in ("daily", "weekly", "monthly", "yearly"):
        return Recurrence(normalized)

    every_n = _EVERY_N.fullmatch(normalized)
    every_one = _EVERY_ONE.fullmatch(normalized)
    if every_n or every_one:
        count = int(every_n.group(1)) if every_n else 1
        unit = (every_n or every_one).group(2 if every_n else 1)
        if count < 1:
            raise ValueError("Recurrence interval must be at least 1.")
        if unit.startswith("day"):
            return Recurrence("every_days", interval=count)
        if unit.startswith("week"):
            return Recurrence("every_weeks", interval=count)
        return Recurrence("every_hours", interval=count)

    tokens = [token for token in re.split(r"[,\s]+", normalized) if token]
    if tokens and all(token in WEEKDAY_INDEX for token in tokens):
        weekdays = tuple(sorted({WEEKDAY_INDEX[token] for token in tokens}))
        return Recurrence("weekdays", weekdays=weekdays)

    raise ValueError(f"Unsupported task frequency: {frequency}")


def _validate_window(window: Window) -> None:
    """Raise if a (start, end) window is empty or inverted."""
    start_time, end_time = window
    if start_time >= end_time:
        raise ValueError("Window start time must be before the end time.")


def _windows_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    """Return whether two half-open [start, end) intervals overlap.

    Touching intervals (one ends exactly where the next begins) do NOT overlap,
    so back-to-back tasks are allowed.
    """
    return first_start < second_end and second_start < first_end


def _clip(window: Window, low: datetime, high: datetime) -> Window:
    """Return ``window`` trimmed to the [low, high] bounds."""
    start, end = window
    return (max(start, low), min(end, high))


def _merge_intervals(intervals: list[Window]) -> list[Window]:
    """Merge overlapping or touching intervals into a sorted, disjoint list."""
    merged: list[Window] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _subtract_intervals(base: Window, blocks: list[Window]) -> list[Window]:
    """Return the parts of ``base`` left free after removing ``blocks``."""
    start, end = base
    free: list[Window] = []
    cursor = start
    for block_start, block_end in _merge_intervals(blocks):
        if block_end <= cursor or block_start >= end:
            continue
        if block_start > cursor:
            free.append((cursor, block_start))
        cursor = max(cursor, block_end)
        if cursor >= end:
            break
    if cursor < end:
        free.append((cursor, end))
    return free


@dataclass(eq=False)
class Task:
    """A single care task for a pet.

    ``due_date`` + ``start_time`` are the source of truth (composed by
    ``start_datetime``). A task is either fixed (runs at ``start_time``) or
    ``flexible`` (the scheduler picks a slot inside ``earliest_start`` ..
    ``latest_end``). ``buffer_minutes`` reserves quiet time after it, and
    ``frequency`` is parsed into a :class:`Recurrence`. Compared by identity
    (``eq=False``) so equal-looking tasks on different pets stay distinct.
    """

    activity_description: str
    due_date: date
    start_time: time
    frequency: str
    duration_minutes: int
    priority: int = 0
    completed: bool = False
    flexible: bool = False
    earliest_start: time | None = None
    latest_end: time | None = None
    buffer_minutes: int = 0
    # Original start date of a recurring series. ``None`` means this task *is*
    # the anchor (its own due_date); occurrences created by the scheduler carry
    # it forward so month-end monthly/yearly rules don't drift off the 31st.
    series_start: date | None = None

    def __post_init__(self) -> None:
        """Validate task details after dataclass initialization."""
        if not self.activity_description.strip():
            raise ValueError("Task activity description cannot be empty.")
        if self.duration_minutes <= 0:
            raise ValueError("Task duration must be greater than 0 minutes.")
        if self.buffer_minutes < 0:
            raise ValueError("Task buffer minutes cannot be negative.")
        parse_recurrence(self.frequency)  # reject an unparseable frequency early
        if self.flexible:
            window_start = self.earliest_start or time.min
            window_end = self.latest_end or time.max
            if window_start >= window_end:
                raise ValueError(
                    "Flexible task earliest_start must be before latest_end."
                )
            window = datetime.combine(date.min, window_end) - datetime.combine(
                date.min, window_start
            )
            if window < timedelta(minutes=self.duration_minutes + self.buffer_minutes):
                raise ValueError(
                    "Flexible task window is shorter than its duration plus buffer."
                )

    @property
    def recurrence(self) -> Recurrence:
        """Return this task's parsed repeat rule."""
        return parse_recurrence(self.frequency)

    @property
    def start_datetime(self) -> datetime:
        """Compose the full start datetime from due_date and start_time."""
        return datetime.combine(self.due_date, self.start_time)

    @property
    def anchor_date(self) -> date:
        """The series' original start date (falls back to this task's due_date)."""
        return self.series_start or self.due_date

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def get_end_time(self) -> datetime:
        """Return the datetime when this task ends."""
        return self.start_datetime + timedelta(minutes=self.duration_minutes)

    def calculate_next_start(self) -> datetime:
        """Return the next occurrence's full datetime for this task's rule."""
        return self.recurrence.next_after(self.start_datetime, anchor=self.anchor_date)

    def calculate_next_due_date(self) -> date:
        """Calculate the next due date based on this task's frequency."""
        return self.calculate_next_start().date()

    def with_due_date(self, due_date: date) -> Task:
        """Return a fresh, incomplete copy of this task on a different date."""
        return self.with_datetime(datetime.combine(due_date, self.start_time))

    def with_start_time(self, start_time: time) -> Task:
        """Return a fresh, incomplete copy of this task at a different time."""
        return self.with_datetime(datetime.combine(self.due_date, start_time))

    def with_datetime(
        self, moment: datetime, *, series_start: date | None = None
    ) -> Task:
        """Return a fresh, incomplete copy of this task at a new date and time.

        ``series_start`` sets the copy's recurrence anchor; leave it ``None``
        (a manual move or a preview copy) to let the copy anchor on its own new
        date. The scheduler passes the original anchor when rolling a recurring
        task forward so month-end rules stay pinned to their day-of-month.
        """
        return Task(
            activity_description=self.activity_description,
            due_date=moment.date(),
            start_time=moment.time(),
            frequency=self.frequency,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            flexible=self.flexible,
            earliest_start=self.earliest_start,
            latest_end=self.latest_end,
            buffer_minutes=self.buffer_minutes,
            series_start=series_start,
        )


@dataclass
class Pet:
    """A pet owned by an :class:`Owner`, holding its own list of tasks."""

    name: str
    species: str
    birth_date: date
    tasks: list[Task] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate pet details after dataclass initialization."""
        if not self.name.strip():
            raise ValueError("Pet name cannot be empty.")
        if not self.species.strip():
            raise ValueError("Pet species cannot be empty.")

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

    def owns(self, task: Task) -> bool:
        """Return whether this exact task instance belongs to this pet."""
        return any(existing is task for existing in self.tasks)


@dataclass
class Owner:
    """A pet owner: their pets plus available/unavailable time windows.

    All pets share the owner's single timeline (the owner can only be in one
    place at a time), which is why ``is_available`` is defined on the owner.
    """

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

    def find_pet_for_task(self, task: Task) -> Pet | None:
        """Return the pet that owns this exact task instance, if any."""
        for pet in self.pets:
            if pet.owns(task):
                return pet
        return None

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

    def save_to_json(self, file_path: str | Path = "data.json") -> None:
        """Save the owner, pets, tasks, and availability windows as JSON."""
        path = Path(file_path)
        path.write_text(
            json.dumps(self._to_json_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load_from_json(cls, file_path: str | Path = "data.json") -> Owner:
        """Load an owner and all saved pets/tasks from a JSON file."""
        path = Path(file_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls._from_json_dict(data)

    def _to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of this owner graph."""
        return {
            "schema_version": 1,
            "owner": {
                "name": self.name,
                "available_windows": [
                    self._window_to_json(window) for window in self.available_windows
                ],
                "unavailable_windows": [
                    self._window_to_json(window)
                    for window in self.unavailable_windows
                ],
                "pets": [self._pet_to_json(pet) for pet in self.pets],
            },
        }

    @classmethod
    def _from_json_dict(cls, data: dict[str, Any]) -> Owner:
        """Rehydrate an owner graph from a JSON-safe dictionary."""
        owner_data = data.get("owner", data)
        owner = cls(name=owner_data.get("name", "Jordan"))

        for window_data in owner_data.get("available_windows", []):
            owner.add_available_window(cls._window_from_json(window_data))
        for window_data in owner_data.get("unavailable_windows", []):
            owner.add_unavailable_window(cls._window_from_json(window_data))

        for pet_data in owner_data.get("pets", []):
            pet = Pet(
                name=pet_data["name"],
                species=pet_data["species"],
                birth_date=date.fromisoformat(pet_data["birth_date"]),
            )
            for task_data in pet_data.get("tasks", []):
                pet.add_task(cls._task_from_json(task_data))
            owner.add_pet(pet)

        return owner

    @staticmethod
    def _pet_to_json(pet: Pet) -> dict[str, Any]:
        """Return a JSON-safe representation of one pet."""
        return {
            "name": pet.name,
            "species": pet.species,
            "birth_date": pet.birth_date.isoformat(),
            "tasks": [Owner._task_to_json(task) for task in pet.get_tasks()],
        }

    @staticmethod
    def _task_to_json(task: Task) -> dict[str, Any]:
        """Return a JSON-safe representation of one task."""
        return {
            "activity_description": task.activity_description,
            "due_date": task.due_date.isoformat(),
            "start_time": task.start_time.isoformat(),
            "frequency": task.frequency,
            "duration_minutes": task.duration_minutes,
            "priority": task.priority,
            "completed": task.completed,
            "flexible": task.flexible,
            "earliest_start": Owner._optional_time_to_json(task.earliest_start),
            "latest_end": Owner._optional_time_to_json(task.latest_end),
            "buffer_minutes": task.buffer_minutes,
            "series_start": (
                task.series_start.isoformat() if task.series_start is not None else None
            ),
        }

    @staticmethod
    def _task_from_json(data: dict[str, Any]) -> Task:
        """Build a task from one JSON task record."""
        return Task(
            activity_description=data["activity_description"],
            due_date=date.fromisoformat(data["due_date"]),
            start_time=time.fromisoformat(data["start_time"]),
            frequency=data["frequency"],
            duration_minutes=int(data["duration_minutes"]),
            priority=int(data.get("priority", 0)),
            completed=bool(data.get("completed", False)),
            flexible=bool(data.get("flexible", False)),
            earliest_start=Owner._optional_time_from_json(data.get("earliest_start")),
            latest_end=Owner._optional_time_from_json(data.get("latest_end")),
            buffer_minutes=int(data.get("buffer_minutes", 0)),
            series_start=(
                date.fromisoformat(data["series_start"])
                if data.get("series_start")
                else None
            ),
        )

    @staticmethod
    def _window_to_json(window: Window) -> dict[str, str]:
        """Return a JSON-safe representation of one time window."""
        start, end = window
        return {"start": start.isoformat(), "end": end.isoformat()}

    @staticmethod
    def _window_from_json(data: dict[str, str]) -> Window:
        """Build a time window from one JSON window record."""
        return (
            datetime.fromisoformat(data["start"]),
            datetime.fromisoformat(data["end"]),
        )

    @staticmethod
    def _optional_time_to_json(value: time | None) -> str | None:
        """Return an ISO time string or None."""
        return value.isoformat() if value is not None else None

    @staticmethod
    def _optional_time_from_json(value: str | None) -> time | None:
        """Return a time from an ISO string or None."""
        return time.fromisoformat(value) if value else None


@dataclass
class PlanEntry:
    """One placed task: where it landed, and where it was originally asked for."""

    pet: Pet
    task: Task
    requested_start: datetime
    moved: bool = False
    flexible: bool = False


@dataclass
class Plan:
    """A schedule where conflicts are reflowed, not dropped.

    ``scheduled`` holds every task that found a slot (moved copies included);
    ``unscheduled`` holds ``(pet, task, reason)`` for the few that couldn't fit.
    """

    scheduled: list[PlanEntry] = field(default_factory=list)
    unscheduled: list[tuple[Pet, Task, str]] = field(default_factory=list)

    def explain(self) -> list[str]:
        """Return human-readable lines describing the plan and its choices."""
        lines: list[str] = []
        for entry in self.scheduled:
            when = entry.task.start_datetime.strftime("%I:%M %p")
            line = f"{when}  {entry.task.activity_description} for {entry.pet.name}"
            if entry.flexible:
                line += " (auto-scheduled)"
            elif entry.moved:
                was = entry.requested_start.strftime("%I:%M %p")
                line += f" (moved from {was})"
            lines.append(line)
        for pet, task, reason in self.unscheduled:
            lines.append(
                f"⚠️  Skipped {task.activity_description} for {pet.name} — {reason}"
            )
        return lines


@dataclass
class Scheduler:
    """Plans an owner's tasks: sorting, filtering, conflict detection,
    recurrence previews, and building an explained, non-overlapping day plan.
    """

    owner: Owner

    def get_all_tasks(self) -> list[Task]:
        """Return every task available through the scheduler's owner."""
        return self.owner.get_all_tasks()

    def sort_by_time(self) -> list[Task]:
        """Return all tasks sorted by start time, with stable tiebreakers."""
        return sorted(
            self.get_all_tasks(),
            key=lambda task: (
                task.start_datetime,
                task.get_end_time(),
                task.activity_description,
            ),
        )

    def filter_tasks(
        self,
        *,
        pet: Pet | None = None,
        pet_name: str | None = None,
        completed: bool | None = None,
        available_only: bool = False,
    ) -> list[Task]:
        """Filter tasks by pet, pet name, completion status, and availability.

        Each criterion is optional: ``None`` means "don't care". ``pet`` matches
        one exact pet instance; ``pet_name`` matches every pet with that name
        (case-insensitive); ``completed`` filters by status. This single method
        covers "filter by pet name" and "filter by status" together.
        """
        if pet is not None:
            pets = [pet]
        elif pet_name is not None:
            wanted = pet_name.strip().lower()
            pets = [p for p in self.owner.get_pets() if p.name.lower() == wanted]
        else:
            pets = self.owner.get_pets()
        source = [task for chosen in pets for task in chosen.get_tasks()]

        result: list[Task] = []
        for task in source:
            if completed is not None and task.completed != completed:
                continue
            if available_only and not self.owner.is_available(
                task.start_datetime, task.get_end_time()
            ):
                continue
            result.append(task)
        return result

    def detect_conflicts(self) -> list[Task]:
        """Return every task whose time range overlaps at least one other.

        Single sweep over start-sorted tasks (O(n log n)). ``active`` holds the
        latest-ending interval still in play; keeping the max end means a task
        that clears ``active`` clears everything earlier too, so nothing is
        missed.
        """
        conflicts: list[Task] = []
        seen: set[Task] = set()
        active: Task | None = None

        for task in self.sort_by_time():
            if active and task.start_datetime < active.get_end_time():
                for conflicting in (active, task):
                    if conflicting not in seen:
                        conflicts.append(conflicting)
                        seen.add(conflicting)

                if task.get_end_time() > active.get_end_time():
                    active = task
            else:
                active = task

        return conflicts

    def find_conflicts(self) -> list[tuple[Task, Task]]:
        """Return every pair of tasks (any pet) whose time ranges overlap.

        Tasks are start-sorted first, so for each task we only compare forward
        until a later task begins after this one ends -- then we stop, because
        everything after it starts even later and cannot overlap either.
        """
        ordered = self.sort_by_time()
        pairs: list[tuple[Task, Task]] = []
        for index, earlier in enumerate(ordered):
            earlier_end = earlier.get_end_time()
            for later in ordered[index + 1 :]:
                if later.start_datetime >= earlier_end:
                    break
                pairs.append((earlier, later))
        return pairs

    def conflict_warnings(self) -> list[str]:
        """Return a readable warning for every overlapping pair of tasks.

        Lightweight and crash-safe: a task that can't be traced back to a pet
        is labelled "Unknown pet" rather than raising, so the UI can always
        show the owner a message instead of erroring out.
        """
        return [
            f"⚠️ Conflict: {self._describe(earlier)} "
            f"overlaps {self._describe(later)}."
            for earlier, later in self.find_conflicts()
        ]

    def _describe(self, task: Task) -> str:
        """Return a short "'Task' (Pet, HH:MM-HH:MM)" label for warnings."""
        pet = self.owner.find_pet_for_task(task)
        pet_name = pet.name if pet is not None else "Unknown pet"
        start = task.start_datetime.strftime("%H:%M")
        end = task.get_end_time().strftime("%H:%M")
        return f"'{task.activity_description}' ({pet_name}, {start}-{end})"

    def schedule_tasks(self) -> list[Task]:
        """Return a non-overlapping schedule, preferring higher priority.

        Greedy by ``(priority desc, start)``: when two tasks collide the more
        important one is placed and the other dropped. Kept tasks stay sorted by
        start so each candidate only needs an O(log k) neighbour check.
        """
        candidates = [
            task
            for task in self.get_all_tasks()
            if not task.completed
            and self.owner.is_available(task.start_datetime, task.get_end_time())
        ]
        candidates.sort(
            key=lambda task: (-task.priority, task.start_datetime, task.get_end_time())
        )

        scheduled: list[Task] = []
        start_times: list[datetime] = []
        for task in candidates:
            start = task.start_datetime
            end = task.get_end_time()
            index = bisect_right(start_times, start)

            if index > 0 and scheduled[index - 1].get_end_time() > start:
                continue
            if index < len(scheduled) and scheduled[index].start_datetime < end:
                continue

            scheduled.insert(index, task)
            start_times.insert(index, start)

        return scheduled

    def build_plan(self, strategy: str = "greedy") -> Plan:
        """Build a non-overlapping plan that reflows conflicts instead of dropping.

        ``strategy="greedy"`` (default) places tasks by ``(priority desc, start)``:
        each is placed at its requested time when the owner is free there, else it
        slides to the earliest open slot that fits.

        ``strategy="optimal"`` first runs weighted interval scheduling over the
        fixed tasks to choose the max-weight non-overlapping set that keeps its
        exact times (so two priority-3 tasks that both fit beat one priority-5
        task that blocks them); the rest are reflowed. Flexible tasks fill gaps.

        Either way, tasks with no free slot at all are left unscheduled with a
        reason, so the plan can explain itself.
        """
        if strategy not in ("greedy", "optimal"):
            raise ValueError(f"Unknown strategy: {strategy!r}")

        candidates = [
            (pet, task)
            for pet in self.owner.get_pets()
            for task in pet.get_tasks()
            if not task.completed
        ]

        if strategy == "optimal":
            holders, _ = self._weighted_interval_selection(
                [task for _, task in candidates if not task.flexible]
            )
            hold_ids: set[int] | None = {id(task) for task in holders}
            # Holders keep their slot first; then other fixed tasks; then flexible.
            candidates.sort(
                key=lambda pair: (
                    0 if id(pair[1]) in hold_ids else 1,
                    pair[1].flexible,
                    self._target_start(pair[1]),
                    pair[1].get_end_time(),
                )
            )
        else:
            hold_ids = None
            # Fixed tasks first (hard times); then earliest deadline (EDF), so
            # time-critical care wins ties; flexible tasks fill the gaps.
            candidates.sort(
                key=lambda pair: (
                    -pair[1].priority,
                    pair[1].flexible,
                    self._deadline(pair[1]),
                    self._target_start(pair[1]),
                    pair[1].get_end_time(),
                )
            )

        plan = Plan()
        placed: list[Window] = []
        for pet, task in candidates:
            requested = task.start_datetime
            footprint = self._footprint(task)  # duration + buffer, the time it locks

            if not task.flexible:
                reserved_end = requested + footprint
                may_hold = hold_ids is None or id(task) in hold_ids
                if (
                    may_hold
                    and self.owner.is_available(requested, reserved_end)
                    and not self._overlaps_any(requested, reserved_end, placed)
                ):
                    plan.scheduled.append(
                        PlanEntry(pet=pet, task=task, requested_start=requested)
                    )
                    placed.append((requested, reserved_end))
                    continue
                slot = self._earliest_free_slot(task, placed, prefer=requested)
            else:
                slot = self._earliest_free_slot(
                    task, placed, window=self._flex_window(task)
                )

            if slot is not None:
                stayed = not task.flexible and slot == requested
                placed_task = task if stayed else task.with_start_time(slot.time())
                plan.scheduled.append(
                    PlanEntry(
                        pet=pet,
                        task=placed_task,
                        requested_start=requested,
                        moved=not task.flexible and not stayed,
                        flexible=task.flexible,
                    )
                )
                placed.append((slot, slot + footprint))
            else:
                plan.unscheduled.append((pet, task, self._unscheduled_reason(task)))

        plan.scheduled.sort(key=lambda entry: entry.task.start_datetime)
        return plan

    @staticmethod
    def _weighted_interval_selection(
        tasks: list[Task],
    ) -> tuple[list[Task], list[Task]]:
        """Return ``(selected, rejected)`` -- the max-weight non-overlapping set.

        Classic weighted interval scheduling in O(n log n): sort by end time,
        find each task's last non-overlapping predecessor by binary search, then
        DP ``best[j] = max(skip, weight_j + best[p(j)])`` and backtrack. Weight is
        ``priority + 1`` so higher priority wins but, among equal priorities, the
        plan keeps *more* tasks rather than fewer. Intervals use each task's
        *footprint* end (duration + buffer), so two tasks the DP calls
        non-overlapping stay non-overlapping once buffers are reserved.
        """
        def footprint_end(task: Task) -> datetime:
            return task.start_datetime + Scheduler._footprint(task)

        ordered = sorted(tasks, key=lambda task: (footprint_end(task), task.start_datetime))
        count = len(ordered)
        if count == 0:
            return [], []

        ends = [footprint_end(task) for task in ordered]
        starts = [task.start_datetime for task in ordered]
        weights = [task.priority + 1 for task in ordered]

        # predecessor[j] = last index i < j whose end <= starts[j] (or -1).
        predecessor = [bisect_right(ends, starts[j], 0, j) - 1 for j in range(count)]

        best = [0] * (count + 1)  # best[j] uses the first j tasks (1-indexed).
        for j in range(1, count + 1):
            include = weights[j - 1] + best[predecessor[j - 1] + 1]
            best[j] = max(best[j - 1], include)

        selected_indexes: list[int] = []
        j = count
        while j > 0:
            include = weights[j - 1] + best[predecessor[j - 1] + 1]
            if include >= best[j - 1]:
                selected_indexes.append(j - 1)
                j = predecessor[j - 1] + 1
            else:
                j -= 1
        chosen = set(selected_indexes)

        selected = [ordered[i] for i in reversed(selected_indexes)]
        rejected = [ordered[i] for i in range(count) if i not in chosen]
        return selected, rejected

    @staticmethod
    def _target_start(task: Task) -> datetime:
        """Preferred start used for ordering and slotting a task."""
        if task.flexible:
            return datetime.combine(task.due_date, task.earliest_start or time.min)
        return task.start_datetime

    @staticmethod
    def _footprint(task: Task) -> timedelta:
        """Return how long a task locks the calendar: its duration plus buffer."""
        return timedelta(minutes=task.duration_minutes + task.buffer_minutes)

    def _deadline(self, task: Task) -> datetime:
        """Return the task's deadline for EDF ordering (earlier = more urgent)."""
        if task.latest_end is not None:
            return datetime.combine(task.due_date, task.latest_end)
        if not task.flexible:
            return task.get_end_time()
        return datetime.max

    def _flex_window(self, task: Task) -> Window:
        """Return a flexible task's allowed [earliest_start, latest_end] window."""
        return (
            datetime.combine(task.due_date, task.earliest_start or time.min),
            datetime.combine(task.due_date, task.latest_end or time.max),
        )

    def _unscheduled_reason(self, task: Task) -> str:
        """Explain why a task could not be placed anywhere."""
        if task.flexible:
            return "no free time slot in its window"
        if not self.owner.is_available(task.start_datetime, task.get_end_time()):
            return "owner unavailable and no free slot"
        return "no free time slot available"

    @staticmethod
    def _overlaps_any(
        start: datetime, end: datetime, windows: list[Window]
    ) -> bool:
        """Return whether [start, end) overlaps any (start, end) in ``windows``."""
        return any(
            _windows_overlap(start, end, other_start, other_end)
            for other_start, other_end in windows
        )

    def _available_bounds(self, day: date) -> list[Window]:
        """Return the owner's available windows clipped to a single day."""
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.min) + timedelta(days=1)  # next midnight
        bounds = [
            _clip(window, day_start, day_end)
            for window in self.owner.get_available_windows()
        ]
        return _merge_intervals([b for b in bounds if b[0] < b[1]])

    def _earliest_free_slot(
        self,
        task: Task,
        placed: list[Window],
        *,
        window: Window | None = None,
        prefer: datetime | None = None,
    ) -> datetime | None:
        """Return the earliest start on the task's day where it fits, or None.

        Free time = the owner's available windows (or the whole day if none are
        set), optionally clipped to ``window``, minus already-placed tasks and
        unavailable windows. Prefers the first opening at or after ``prefer``
        (defaulting to the window start / requested time), else the earliest.
        """
        day = task.due_date
        duration = self._footprint(task)  # reserve duration + buffer
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.min) + timedelta(days=1)  # next midnight

        bounds = self._available_bounds(day) or [(day_start, day_end)]
        if window is not None:
            clipped = [_clip(bound, window[0], window[1]) for bound in bounds]
            bounds = [bound for bound in clipped if bound[0] < bound[1]]

        busy = [
            _clip(taken, day_start, day_end)
            for taken in placed + self.owner.get_unavailable_windows()
            if _windows_overlap(taken[0], taken[1], day_start, day_end)
        ]

        free = sorted(
            (opening_start, opening_end)
            for bound in bounds
            for opening_start, opening_end in _subtract_intervals(bound, busy)
            if opening_end - opening_start >= duration
        )
        if not free:
            return None

        target = prefer or (window[0] if window is not None else task.start_datetime)
        for opening_start, opening_end in free:
            candidate = max(opening_start, target)
            if candidate + duration <= opening_end:
                return candidate
        # Nothing opens at or after the target time. A flexible task's target is
        # its window start, so the loop above already covered its whole window;
        # a fixed task must never be slid *backwards* before the time it asked
        # for. Either way, report it unschedulable rather than move it earlier.
        return None

    def occurrences_between(
        self, start: date, end: date
    ) -> list[tuple[Pet, Task]]:
        """Project occurrences in [start, end] without mutating any pet.

        Each task's :class:`Recurrence` jumps straight to the first occurrence in
        range (O(1) for date/hour cadences) and yields fresh, unattached copies,
        so this is safe to call for previews and supports every-N, weekday, and
        multiple-times-per-day rules.
        """
        if start > end:
            raise ValueError("Start date cannot be after end date.")

        window_start = datetime.combine(start, time.min)
        window_end = datetime.combine(end, time.max)

        occurrences: list[tuple[Pet, Task]] = []
        for pet in self.owner.get_pets():
            for task in pet.get_tasks():
                for moment in task.recurrence.occurrences_in(
                    task.start_datetime, window_start, window_end
                ):
                    occurrences.append((pet, task.with_datetime(moment)))

        occurrences.sort(
            key=lambda pair: (pair[1].start_datetime, pair[1].activity_description)
        )
        return occurrences

    def mark_task_complete(self, task: Task) -> None:
        """Mark a task complete and create its next occurrence when recurring."""
        task.mark_complete()
        self.create_next_occurrence(task)

    def create_next_occurrence(self, task: Task) -> Task | None:
        """Create and attach the next recurring occurrence for a task."""
        if not task.recurrence.is_recurring:
            return None

        # Carry the series anchor forward so a clamped month-end occurrence
        # (Feb 28) still rolls to the anchored next one (Mar 31, not Mar 28).
        next_task = task.with_datetime(
            task.calculate_next_start(), series_start=task.anchor_date
        )

        pet = self.owner.find_pet_for_task(task)
        if pet is not None:
            pet.add_task(next_task)

        return next_task

    def create_next_occurence(self, task: Task) -> Task | None:
        """Call create_next_occurrence using the older misspelled name."""
        return self.create_next_occurrence(task)
