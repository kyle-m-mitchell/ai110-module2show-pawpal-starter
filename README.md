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

## 🖥️ Sample Output

Running `python main.py` walks through the scheduler. A few highlights:

**A generated plan that reflows conflicts instead of dropping them** (nothing lost — one task moved off a clash, one flexible task auto-placed):
```
Suggested plan (higher priority wins, nothing dropped)
------------------------------------------------------
  08:15 AM  Vet call for Biscuit
  08:35 AM  Morning walk for Biscuit (moved from 08:00 AM)
  09:05 AM  Feed breakfast for Mochi (moved from 09:00 AM)
  12:00 PM  Playtime for Biscuit (auto-scheduled)
  05:30 PM  Brush fur for Biscuit
```

**Greedy vs. optimal packing** when the day is tight (only 08:00–10:00 free, so a task must be dropped):
```
Greedy:
  08:30 AM  Grooming (priority 5)
  ⚠️  Skipped Walk (priority 3) — no free time slot available
  ⚠️  Skipped Training (priority 3) — no free time slot available

Optimal:
  08:00 AM  Walk (priority 3)
  09:00 AM  Training (priority 3)
  ⚠️  Skipped Grooming (priority 5) — no free time slot available
```

**Richer recurrence grammar** (`every 8 hours`, `every 2 days`, `mon,thu`) and **buffer** gaps:
```
  Sun 07-05 06:00 AM  Meds (every 8 hours)
  Mon 07-06 09:00 AM  Grooming (mon,thu)
  Tue 07-07 09:00 AM  Deworm (every 2 days)

  10:00 AM  Vet visit for Mochi
  10:50 AM  Feed for Mochi (moved from 10:30 AM)   # 20-min buffer after the vet visit
```

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
collected 56 items                          

tests/test_edge_cases.py ............ [ 21%]
...........                           [ 41%]
tests/test_pawpal.py ................ [ 69%]
.................                     [100%]

============ 56 passed in 0.17s =============
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

## 📸 Demo Walkthrough

Describe your app in numbered steps so a reader can follow along without watching a video:

1. <!-- Describe this step -->
2. <!-- Describe this step -->
3. <!-- Describe this step -->
4. <!-- Describe this step -->
5. <!-- Add more steps as needed -->

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
