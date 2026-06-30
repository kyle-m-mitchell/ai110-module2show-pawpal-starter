from datetime import date, datetime

from pawpal_system import Pet, Task


def test_mark_complete_changes_task_status():
    task = Task(
        activity_description="Morning walk",
        time=datetime(2026, 6, 30, 8, 0),
        frequency="daily",
        duration_minutes=30,
        due_date=date(2026, 6, 30),
    )

    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_adding_task_to_pet_increases_task_count():
    pet = Pet(species="dog", birth_date=date(2020, 5, 14))
    task = Task(
        activity_description="Feed breakfast",
        time=datetime(2026, 6, 30, 9, 0),
        frequency="daily",
        duration_minutes=10,
        due_date=date(2026, 6, 30),
    )

    starting_task_count = len(pet.get_tasks())

    pet.add_task(task)

    assert len(pet.get_tasks()) == starting_task_count + 1
    assert task in pet.get_tasks()
