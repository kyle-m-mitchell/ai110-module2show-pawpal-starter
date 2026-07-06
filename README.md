# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## Features

- **Pet and task tracking:** Create an owner profile, add pets, and attach care tasks with due dates, start times, duration, frequency, priority, completion status, flexible scheduling windows, and buffer time.
- **JSON persistence:** PawPal+ saves the owner, pets, tasks, completion state, recurrence anchors, buffers, and availability windows to `data.json` so they are still there after the app restarts.
- **Friendly CLI formatting:** `main.py` prints structured tables, task-type emojis, color-coded statuses, and color-coded priorities for easier terminal demos.
- **Sorting by time:** `Scheduler.sort_by_time()` orders tasks by start datetime, then end time, then description so the UI and CLI show a stable chronological schedule.
- **Task filtering:** `Scheduler.filter_tasks()` filters by pet, pet name, completion status, and owner availability, which powers the Streamlit task table controls.
- **Conflict warnings:** `Scheduler.find_conflicts()` returns overlapping task pairs, while `conflict_warnings()` turns those pairs into readable alerts before the user generates a plan.
- **Priority-based daily planning:** `Scheduler.build_plan(strategy="greedy")` places higher-priority tasks first, keeps non-conflicting tasks in order, and reflows lower-priority conflicts into the next free slot instead of dropping them.
- **Optimal schedule option:** `build_plan(strategy="optimal")` uses weighted interval scheduling to keep the highest total priority set when the day is too tight for every fixed task.
- **Flexible task placement:** Flexible tasks can define an earliest start and latest end; the scheduler searches free intervals and auto-places them in the earliest slot that fits.
- **Recurring care support:** `Recurrence` handles daily, weekly, monthly, yearly, `every N days/weeks/hours`, and weekday-set schedules such as `mon,thu`.
- **Fast recurrence previews:** `occurrences_between()` jumps to the first matching occurrence inside the preview range instead of stepping through every past recurrence.
- **Buffers and availability windows:** The planner reserves `duration + buffer_minutes`, subtracts unavailable windows, and uses free-interval calculations so tasks do not stack unrealistically.

## Persistence Workflow

PawPal+ stores user-entered data in a local `data.json` file at the project root.

1. When `app.py` starts, `initialize_session_state()` calls `Owner.load_from_json("data.json")` if the file exists.
2. If no saved file exists, the app starts with the default owner, `Jordan`.
3. When the user changes the owner name, adds a pet, or adds a task, the app calls `Owner.save_to_json("data.json")`.
4. The next time the Streamlit app runs, the saved owner, pets, tasks, flexible windows, recurrence settings, completion statuses, buffers, and availability windows are restored.
5. Generated plans are not saved because they are derived from the current task list; users can regenerate them at any time.

Files modified for persistence:

- `pawpal_system.py`: added `Owner.save_to_json()` and `Owner.load_from_json()` plus helper serialization logic for pets, tasks, dates, times, and windows.
- `app.py`: loads `data.json` on startup and saves after owner, pet, or task changes.
- `tests/test_pawpal.py`: adds a JSON round-trip test to verify saved data loads back with the same pets, tasks, windows, and task settings.
- `README.md`: documents the persistence workflow.

## CLI Formatting Features

The command-line demo in `main.py` now has user-friendly terminal output without adding a new package dependency.

- `format_table()` builds structured ASCII tables for task lists, generated plans, strategy comparisons, recurrence previews, and buffer examples.
- `task_icon()` adds category emojis such as `🐕` for walks/training, `🍽️` for feeding, `💊` for medication, `🩺` for vet care, `🎾` for play, and `🧼` for grooming.
- `status_badge()` displays task states as `✅ done`, `🟡 todo`, or `🔵 flexible`.
- `priority_badge()` labels priorities as `low`, `med`, or `high`.
- `color_text()` and `supports_color()` use ANSI colors when the output is an interactive terminal and automatically fall back to plain text for captured output or environments with `NO_COLOR` set.

No external formatting library was added; the table output is implemented directly in `main.py` so the project still only requires `streamlit` and `pytest`.

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
python3 -m pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```
% python3 -m pytest
============ test session starts ============
platform darwin -- Python 3.14.5, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/kylemitchell/ai110-module2show-pawpal-starter
plugins: anyio-4.13.0
collected 57 items                          

tests/test_edge_cases.py .......................                         [ 40%]
tests/test_pawpal.py ..................................                  [100%]

============ 57 passed in 0.18s =============
```

**Reliability Confidence Level (1-5)**
5


## 📐 Smarter Scheduling

How each behavior works today (see [`pawpal_system.py`](pawpal_system.py)):

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `Scheduler.sort_by_time` ([pawpal_system.py:477](pawpal_system.py#L477)) | Sorted by `(start_datetime, end_time, description)` for a stable tiebreak. |
| Filtering | `Scheduler.filter_tasks` ([pawpal_system.py:488](pawpal_system.py#L488)) | One method, optional criteria: by `pet`, by `pet_name` (case-insensitive), by `completed`, and `available_only`. `None` means "don't care". |
| Conflict handling | `detect_conflicts` ([pawpal_system.py:523](pawpal_system.py#L523)), `find_conflicts` / `conflict_warnings` ([:549](pawpal_system.py#L549)) | O(n log n) sweep flags clashing tasks; `conflict_warnings` returns crash-safe, human-readable "X overlaps Y" messages. |
| Recurring tasks | `Recurrence` ([pawpal_system.py:49](pawpal_system.py#L49)), `occurrences_between` ([:864](pawpal_system.py#L864)), `create_next_occurrence` ([:898](pawpal_system.py#L898)) | daily/weekly/monthly/yearly, `every N days/weeks/hours`, weekday sets (`mon,thu`); monthly clamps to month-end; previews don't mutate stored tasks. |
| Planning | `Scheduler.build_plan(strategy=...)` ([pawpal_system.py:621](pawpal_system.py#L621)) | Returns a `Plan` (scheduled + `unscheduled=[(pet, task, reason)]`) that reflows conflicts instead of dropping them and explains itself via `Plan.explain()`. |

### ✅ Smarter-scheduling upgrades (all shipped)

Each upgrade is *what was too simple → the algorithm → cost → why it helps a pet owner*.
Test count grew from 10 → 29 as these landed.

**Tier 1 — biggest payoff**

1. **Don't drop tasks — reflow + explain.** `schedule_tasks` used to silently drop the conflict loser. `build_plan` ([pawpal_system.py:621](pawpal_system.py#L621)) now builds **free intervals** (available − unavailable − placed) via `_merge_intervals` / `_subtract_intervals` and **first-fits** the loser into the next gap, returning `Plan.scheduled` (with a `moved` flag) + `Plan.unscheduled` with reasons. O(n log n). *The app says "Morning walk moved from 08:00 AM" or "Skipped … — no free slot."*
2. **Flexible placement.** New `Task.flexible` / `earliest_start` / `latest_end`; `_earliest_free_slot` ([pawpal_system.py:817](pawpal_system.py#L817)) auto-places a flexible task in the earliest free gap inside its window. O(n log n). *Enter "20-min walk, anytime 8am–6pm" and PawPal picks the time.*

**Tier 2 — smarter core algorithm**

3. **Optimal packing (weighted interval scheduling DP).** `build_plan(strategy="optimal")` runs `_weighted_interval_selection` ([pawpal_system.py:719](pawpal_system.py#L719)): sort by end time, binary-search each task's last non-overlapping predecessor, `best[j] = max(skip, weight_j + best[p(j)])`, backtrack. Weight = `priority + 1`. O(n log n). *Two priority-3 tasks that both fit beat one priority-5 task that blocks them.*
4. **Conflict clustering / pairs.** `find_conflicts` ([pawpal_system.py:549](pawpal_system.py#L549)) returns overlapping **pairs**; `conflict_warnings` turns them into "'Vet call' overlaps 'Morning walk'". *Actionable, and crash-safe.*

**Tier 3 — recurrence**

5. **O(1) jump to the first occurrence.** `Recurrence._first_on_or_after` ([pawpal_system.py:49](pawpal_system.py#L49)) jumps into the window (timedelta division / month math / ≤8-day weekday scan) instead of the old per-period `while` loop. *A task due in 2000 previews a 2026 window instantly.*
6. **Richer recurrence grammar.** `parse_recurrence` ([pawpal_system.py:162](pawpal_system.py#L162)) understands `every N days/weeks/hours`, weekday sets (`mon,thu`), and multiple-times-per-day (`every 8 hours`). *Matches real care — grooming Mon/Thu, meds every 8h.*

**Tier 4 — supporting primitives & smaller wins**

7. **Free-interval / availability merge primitive.** `_merge_intervals` / `_subtract_intervals` / `_clip` (sort + linear merge, O(w log w)) underpin #1, #2 and buffers.
8. **Buffer / transition time.** `Task.buffer_minutes`; the planner reserves a `_footprint` of `duration + buffer` so tasks never stack (a walk then a vet visit get a real gap between).
9. **Deadline-aware ordering (EDF).** `_deadline` breaks ties in `build_plan` by **earliest deadline first**, so time-critical care (a task with a tight `latest_end`) wins the slot.

## Demo Walkthrough

The Streamlit app in `app.py` is the main user interface for PawPal+. A user can:

- Enter the owner's name and add pets with a name, species, and birth date.
- Add tasks for a selected pet, including due date, start time, duration, priority, frequency, optional buffer time, and optional flexible scheduling window.
- View all tasks in a sorted table, then filter the table by pet, completion status, or owner availability.
- See conflict warnings before generating a plan, including which tasks overlap, how long they overlap, and which one has the higher priority.
- Generate a daily plan using either the greedy strategy or the optimal strategy.
- Review the plan in a table that shows scheduled tasks, moved tasks, auto-scheduled flexible tasks, and skipped tasks with reasons.
- Preview upcoming recurring task occurrences for the next 1-30 days.

Example workflow:

1. Add an owner named `Jordan`.
2. Add two pets: `Biscuit` the dog and `Mochi` the cat.
3. Add a morning walk for Biscuit at 8:00 AM and a higher-priority vet call at 8:15 AM.
4. Add a breakfast task for Mochi and a flexible playtime task for Biscuit.
5. Review the sorted task table and conflict warning.
6. Click **Generate plan** to see PawPal+ keep the higher-priority vet call, move the walk into the next free slot, and auto-place the flexible playtime task.
7. Use the upcoming preview to confirm recurring tasks such as daily walks or `every 8 hours` medication.

Key scheduler behaviors shown in the walkthrough:

- **Sorting by time:** Tasks appear chronologically even when they were added out of order.
- **Filtering:** The same task list can be narrowed by pet, status, or availability.
- **Conflict warnings:** Overlapping tasks are detected as task pairs before a plan is generated.
- **Priority-aware planning:** Higher-priority tasks keep their slot when a conflict occurs.
- **Reflow instead of drop:** Lower-priority conflicts are moved into the next free slot when possible.
- **Flexible scheduling:** Tasks marked flexible are auto-placed inside their allowed time window.
- **Recurring previews:** Future task occurrences are projected without mutating the saved task list.
- **Buffer time:** The planner reserves extra transition time after a task, so following tasks move later when needed.

Sample CLI output from running `python3 main.py` shown without ANSI colors:

```text
All tasks, sorted by time
=========================
+---------------------+---------+-------------------+----------+----------+------------+
| Time                | Pet     | Task              | Duration | Priority | Status     |
+---------------------+---------+-------------------+----------+----------+------------+
| 08:00 AM - 08:30 AM | Biscuit | 🐕 Morning walk    | 30 min   | low 0    | 🟡 todo     |
| 08:15 AM - 08:35 AM | Biscuit | 🩺 Vet call        | 20 min   | high 5   | 🟡 todo     |
| 09:00 AM - 09:10 AM | Mochi   | 🍽️ Feed breakfast | 10 min   | low 0    | 🟡 todo     |
| 12:00 PM - 12:45 PM | Biscuit | 🎾 Playtime        | 45 min   | low 0    | 🔵 flexible |
| 05:30 PM - 05:50 PM | Biscuit | 🧼 Brush fur       | 20 min   | low 0    | 🟡 todo     |
+---------------------+---------+-------------------+----------+----------+------------+

Biscuit's tasks (filter by pet name)
====================================
+---------------------+---------+----------------+----------+----------+------------+
| Time                | Pet     | Task           | Duration | Priority | Status     |
+---------------------+---------+----------------+----------+----------+------------+
| 05:30 PM - 05:50 PM | Biscuit | 🧼 Brush fur    | 20 min   | low 0    | 🟡 todo     |
| 08:00 AM - 08:30 AM | Biscuit | 🐕 Morning walk | 30 min   | low 0    | 🟡 todo     |
| 08:15 AM - 08:35 AM | Biscuit | 🩺 Vet call     | 20 min   | high 5   | 🟡 todo     |
| 12:00 PM - 12:45 PM | Biscuit | 🎾 Playtime     | 45 min   | low 0    | 🔵 flexible |
+---------------------+---------+----------------+----------+----------+------------+

Schedule check
==============
  ⚠️ Conflict: 'Morning walk' (Biscuit, 08:00-08:30) overlaps 'Vet call' (Biscuit, 08:15-08:35).

Suggested plan (higher priority wins, nothing dropped)
======================================================
+----------+---------+-------------------+----------+---------------------+
| Start    | Pet     | Task              | Priority | Result              |
+----------+---------+-------------------+----------+---------------------+
| 08:15 AM | Biscuit | 🩺 Vet call        | high 5   | kept requested time |
| 08:35 AM | Biscuit | 🐕 Morning walk    | low 0    | moved from 08:00 AM |
| 09:05 AM | Mochi   | 🍽️ Feed breakfast | low 0    | moved from 09:00 AM |
| 12:00 PM | Biscuit | 🎾 Playtime        | low 0    | auto-scheduled      |
| 05:30 PM | Biscuit | 🧼 Brush fur       | low 0    | kept requested time |
+----------+---------+-------------------+----------+---------------------+

Greedy vs. Optimal (only 08:00-10:00 free)
==========================================
Greedy:
+-------------+---------+------------+----------+-----------------------------+
| Start       | Pet     | Task       | Priority | Result                      |
+-------------+---------+------------+----------+-----------------------------+
| 08:30 AM    | Biscuit | 🧼 Grooming | high 5   | kept requested time         |
| unscheduled | Biscuit | 🐕 Walk     | med 3    | no free time slot available |
| unscheduled | Biscuit | 🐕 Training | med 3    | no free time slot available |
+-------------+---------+------------+----------+-----------------------------+

Optimal:
+-------------+---------+------------+----------+-----------------------------+
| Start       | Pet     | Task       | Priority | Result                      |
+-------------+---------+------------+----------+-----------------------------+
| 08:00 AM    | Biscuit | 🐕 Walk     | med 3    | kept requested time         |
| 09:00 AM    | Biscuit | 🐕 Training | med 3    | kept requested time         |
| unscheduled | Biscuit | 🧼 Grooming | high 5   | no free time slot available |
+-------------+---------+------------+----------+-----------------------------+

Upcoming occurrences (next 2 days) — richer recurrence grammar
==============================================================
+--------------------+---------+------------+---------------+
| When               | Pet     | Task       | Frequency     |
+--------------------+---------+------------+---------------+
| Mon 07-06 06:00 AM | Biscuit | 💊 Meds     | every 8 hours |
| Mon 07-06 09:00 AM | Biscuit | 💊 Deworm   | every 2 days  |
| Mon 07-06 09:00 AM | Biscuit | 🧼 Grooming | mon,thu       |
| Mon 07-06 02:00 PM | Biscuit | 💊 Meds     | every 8 hours |
+--------------------+---------+------------+---------------+

Buffer keeps tasks from stacking
================================
Buffered plan
=============
+----------+-------+-------------+----------+---------------------+
| Start    | Pet   | Task        | Priority | Result              |
+----------+-------+-------------+----------+---------------------+
| 10:00 AM | Mochi | 🩺 Vet visit | high 5   | kept requested time |
| 10:50 AM | Mochi | 🍽️ Feed     | low 1    | moved from 10:30 AM |
+----------+-------+-------------+----------+---------------------+
```
