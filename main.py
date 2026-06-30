from datetime import date, datetime

from pawpal_system import Owner, Pet, Scheduler, Task


def find_pet_for_task(owner: Owner, task: Task) -> Pet | None:
    for pet in owner.get_pets():
        if task in pet.get_tasks():
            return pet

    return None


def main() -> None:
    today = date.today()

    owner = Owner(name="Jordan")

    dog = Pet(species="dog", birth_date=date(2020, 5, 14))
    cat = Pet(species="cat", birth_date=date(2022, 9, 3))

    morning_walk = Task(
        activity_description="Morning walk",
        time=datetime.combine(today, datetime.strptime("08:00", "%H:%M").time()),
        frequency="daily",
        duration_minutes=30,
        due_date=today,
    )
    cat_breakfast = Task(
        activity_description="Feed breakfast",
        time=datetime.combine(today, datetime.strptime("09:00", "%H:%M").time()),
        frequency="daily",
        duration_minutes=10,
        due_date=today,
    )
    grooming = Task(
        activity_description="Brush fur",
        time=datetime.combine(today, datetime.strptime("17:30", "%H:%M").time()),
        frequency="weekly",
        duration_minutes=20,
        due_date=today,
    )

    dog.add_tasks([morning_walk, grooming])
    cat.add_task(cat_breakfast)

    owner.add_pet(dog)
    owner.add_pet(cat)

    scheduler = Scheduler(owner=owner)

    print("Today's Schedule")
    print("----------------")

    for task in scheduler.schedule_tasks():
        pet = find_pet_for_task(owner, task)
        pet_label = pet.species.title() if pet else "Unknown pet"
        start_time = task.time.strftime("%I:%M %p")
        end_time = task.get_end_time().strftime("%I:%M %p")

        print(
            f"{start_time}-{end_time}: {task.activity_description} "
            f"for {pet_label} ({task.duration_minutes} min)"
        )


if __name__ == "__main__":
    main()
