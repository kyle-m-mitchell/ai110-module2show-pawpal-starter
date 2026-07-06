# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

I asked the agent to review the final PawPal+ files and think about what advanced scheduling capabilities a modern user would expect from a pet-care planning app. I specifically wanted the app to feel less like a basic to-do list and more like a smart assistant for Millennial / Gen-Z users: quick, explainable, flexible, visually clear, and able to prevent scheduling problems before they happen.

The main goal was to connect the Streamlit UI to the stronger algorithms in my `Scheduler` class and document the advanced features I added, including sorting, filtering, conflict warnings, recurrence, flexible placement, buffer time, and smarter daily planning.

**What did the agent do?**

- Reviewed the project files, including `pawpal_system.py`, `app.py`, `tests/test_pawpal.py`, `tests/test_edge_cases.py`, `README.md`, `reflection.md`, and the UML diagrams.
- Identified the modern capabilities that would make PawPal+ feel more useful: chronological task sorting, pet/status/availability filtering, professional warning messages, recurring care previews, flexible "anytime between" scheduling, automatic conflict reflow, and an optional optimal scheduling mode.
- Updated `app.py` so the task display uses `Scheduler.sort_by_time()` and `Scheduler.filter_tasks()` instead of duplicating scheduling logic in the UI.
- Added Streamlit feedback components such as `st.success`, `st.warning`, and `st.table` so sorted data, filtered data, plan results, and conflicts look more polished.
- Improved conflict presentation by showing one clear warning summary plus a structured conflict table with each overlapping pair, pet names, time ranges, overlap length, and priority information.
- Updated the UML to match the final class design, including `Window`, `Plan`, `PlanEntry`, optional flexible-task fields, and the way `Scheduler` coordinates tasks, conflicts, availability windows, and plans.
- Ran verification commands such as `python3 -m compileall app.py`, `python3 -m pytest`, and `python3 main.py` to confirm the code and examples matched the final behavior.

**What did you have to verify or fix manually?**

I had to verify that the agent's suggestions matched what the application actually implemented. For example, I checked that the README and UML did not claim features that only sounded nice but were not in the code. I also reviewed whether the "modern" enhancements were realistic for this project: the app now has smart scheduling, conflict visibility, recurrence previews, and explainable planning, but it does not yet have push notifications, calendar sync, accounts, or mobile persistence.

I also had to verify the exact behavior with tests and CLI output. The automated tests confirmed the scheduler handles conflicts, recurrence, flexible windows, buffers, availability, invalid inputs, and optimal scheduling edge cases. The `main.py` output helped confirm that the demo text was accurate: tasks are sorted, conflicts are detected, higher-priority tasks keep their slot, lower-priority tasks are reflowed, flexible tasks are auto-scheduled, and recurring tasks can be previewed.

One issue I had to watch for was that UI improvements should not replace the core class logic. The final version keeps the algorithms inside `Scheduler` and uses Streamlit mainly for presentation, which is a better design because the app interface does not become responsible for sorting, filtering, or conflict detection.

---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | | |
| **Prompt** | | |
| **Response summary** | | |
| **What was useful** | | |
| **Problems noticed** | | |
| **Decision** | | |

**Which approach did you use in your final implementation and why?**

<!-- Your conclusion -->
