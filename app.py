from datetime import date, time, timedelta

import streamlit as st

from pawpal_system import Owner, Pet, Plan, Scheduler, Task


def initialize_session_state() -> None:
    """Create persistent Streamlit objects the first time the app runs."""
    if "owner" not in st.session_state or not isinstance(
        st.session_state.owner, Owner
    ):
        st.session_state.owner = Owner(name="Jordan")
    else:
        for index, pet in enumerate(st.session_state.owner.get_pets()):
            if not hasattr(pet, "name"):
                pet.name = f"{pet.species.title()} #{index + 1}"

    if "plan" not in st.session_state:
        st.session_state.plan = None


def pet_label(pet: Pet) -> str:
    """Return a readable label for a pet."""
    return f"{pet.name} ({pet.species})"


def flex_label(task: Task) -> str:
    """Return a readable flexibility window for a task, or 'no'."""
    if not task.flexible:
        return "no"
    earliest = task.earliest_start.strftime("%I:%M %p") if task.earliest_start else "any"
    latest = task.latest_end.strftime("%I:%M %p") if task.latest_end else "any"
    return f"{earliest}–{latest}"


def task_rows(owner: Owner) -> list[dict[str, str | int]]:
    """Return table rows for every task owned by every pet."""
    rows: list[dict[str, str | int]] = []

    for pet in owner.get_pets():
        for task in pet.get_tasks():
            rows.append(
                {
                    "Pet": pet_label(pet),
                    "Task": task.activity_description,
                    "Date": task.due_date.isoformat(),
                    "Start": task.start_datetime.strftime("%I:%M %p"),
                    "End": task.get_end_time().strftime("%I:%M %p"),
                    "Frequency": task.frequency,
                    "Duration": task.duration_minutes,
                    "Buffer": task.buffer_minutes,
                    "Priority": task.priority,
                    "Flexible": flex_label(task),
                    "Done": "yes" if task.completed else "no",
                }
            )

    return rows


def plan_rows(plan: Plan) -> list[dict[str, str | int]]:
    """Return table rows for a built plan, flagging any auto-moved tasks."""
    rows: list[dict[str, str | int]] = []
    for entry in plan.scheduled:
        if entry.flexible:
            note = "auto-scheduled"
        elif entry.moved:
            note = f"moved from {entry.requested_start.strftime('%I:%M %p')}"
        else:
            note = ""
        rows.append(
            {
                "Pet": pet_label(entry.pet),
                "Task": entry.task.activity_description,
                "Start": entry.task.start_datetime.strftime("%I:%M %p"),
                "End": entry.task.get_end_time().strftime("%I:%M %p"),
                "Duration": entry.task.duration_minutes,
                "Priority": entry.task.priority,
                "Note": note,
            }
        )
    return rows


st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
initialize_session_state()

owner = st.session_state.owner

st.title("🐾 PawPal+")

owner.name = st.text_input("Owner name", value=owner.name)

st.divider()

st.subheader("Pets")

pet_col_1, pet_col_2, pet_col_3 = st.columns(3)
with pet_col_1:
    pet_name = st.text_input("Pet name", value="Mochi")
with pet_col_2:
    species = st.selectbox("Species", ["dog", "cat", "other"])
with pet_col_3:
    birth_date = st.date_input("Birth date", value=date(2020, 1, 1))

if st.button("Add pet"):
    if not pet_name.strip():
        st.error("Pet name cannot be empty.")
    else:
        owner.add_pet(
            Pet(name=pet_name.strip(), species=species, birth_date=birth_date)
        )
        st.session_state.plan = None
        st.success(f"Added {pet_name.strip()}.")

if owner.get_pets():
    st.table(
        [
            {
                "Name": pet.name,
                "Species": pet.species,
                "Birth date": pet.birth_date.isoformat(),
                "Tasks": len(pet.get_tasks()),
            }
            for pet in owner.get_pets()
        ]
    )
else:
    st.info("No pets added yet.")

st.divider()

st.subheader("Tasks")

pets = owner.get_pets()
if pets:
    selected_pet_index = st.selectbox(
        "Pet",
        options=range(len(pets)),
        format_func=lambda index: pet_label(pets[index]),
    )
    selected_pet = pets[selected_pet_index]

    with st.form("add_task_form", clear_on_submit=True):
        task_col_1, task_col_2 = st.columns(2)
        with task_col_1:
            task_title = st.text_input("Task", value="Morning walk")
            task_date = st.date_input("Due date", value=date.today())
            frequency = st.text_input(
                "Frequency",
                value="daily",
                help=(
                    "once, daily, weekly, monthly, yearly, "
                    "'every 2 days', 'every 8 hours', or weekdays like 'mon,thu'"
                ),
            )
        with task_col_2:
            task_time = st.time_input("Start time", value=time(8, 0))
            duration = st.number_input(
                "Duration minutes", min_value=1, max_value=240, value=20
            )
            priority = st.number_input(
                "Priority (higher wins conflicts)", min_value=0, max_value=5, value=0
            )
            buffer_minutes = st.number_input(
                "Buffer minutes (quiet gap after task)",
                min_value=0,
                max_value=120,
                value=0,
            )

        flexible = st.checkbox("Flexible time (let PawPal pick the slot)", value=False)
        flex_col_1, flex_col_2 = st.columns(2)
        with flex_col_1:
            earliest = st.time_input("Earliest start", value=time(8, 0))
        with flex_col_2:
            latest = st.time_input("Latest end", value=time(18, 0))
        st.caption("Earliest / Latest apply only when Flexible is checked.")

        submitted = st.form_submit_button("Add task")

    if submitted:
        if not task_title.strip():
            st.error("Task name cannot be empty.")
        else:
            try:
                task = Task(
                    activity_description=task_title,
                    due_date=task_date,
                    start_time=task_time,
                    frequency=frequency,
                    duration_minutes=int(duration),
                    priority=int(priority),
                    flexible=flexible,
                    earliest_start=earliest if flexible else None,
                    latest_end=latest if flexible else None,
                    buffer_minutes=int(buffer_minutes),
                )
            except ValueError as error:
                st.error(str(error))
            else:
                selected_pet.add_task(task)
                st.session_state.plan = None
                st.success(f"Added {task.activity_description}.")

    rows = task_rows(owner)
    if rows:
        st.table(rows)
    else:
        st.info("No tasks added yet.")
else:
    st.info("Add a pet before creating tasks.")

st.divider()

st.subheader("Build Schedule")

strategy = st.radio(
    "Strategy",
    options=["greedy", "optimal"],
    format_func=lambda choice: {
        "greedy": "Greedy (priority first, reflow)",
        "optimal": "Optimal (max total priority)",
    }[choice],
    horizontal=True,
)

if st.button("Generate plan"):
    st.session_state.plan = Scheduler(owner=owner).build_plan(strategy=strategy)

plan = st.session_state.plan
if plan is not None and (plan.scheduled or plan.unscheduled):
    st.markdown("### Today's Plan")

    if plan.scheduled:
        st.table(plan_rows(plan))
        moved = [entry for entry in plan.scheduled if entry.moved]
        if moved:
            st.caption(
                f"↪ {len(moved)} task(s) were moved to avoid a conflict "
                "instead of being dropped — see the Note column."
            )

    for pet, task, reason in plan.unscheduled:
        st.warning(
            f"Skipped **{task.activity_description}** for {pet_label(pet)} — {reason}."
        )
else:
    st.info("No plan yet. Click **Generate plan**.")

st.divider()

st.subheader("Upcoming (preview)")

preview_days = st.slider("Days ahead", min_value=1, max_value=30, value=7)

if owner.get_pets():
    start = date.today()
    end = start + timedelta(days=preview_days)
    upcoming = Scheduler(owner=owner).occurrences_between(start, end)
    if upcoming:
        st.table(
            [
                {
                    "Pet": pet_label(pet),
                    "Task": task.activity_description,
                    "Date": task.due_date.isoformat(),
                    "Start": task.start_datetime.strftime("%I:%M %p"),
                    "End": task.get_end_time().strftime("%I:%M %p"),
                    "Frequency": task.frequency,
                }
                for pet, task in upcoming
            ]
        )
    else:
        st.info("No occurrences in this window.")
else:
    st.info("Add a pet to preview upcoming tasks.")
