from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from mealie.schema.household.group_shopping_list import ShoppingListSave
from mealie.schema.meal_plan.new_meal import SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def today() -> date:
    """`date.today()` is naive; the app reasons in UTC, so tests should too."""

    return datetime.now(UTC).date()


def enable_attendance(api_client: TestClient, user: TestUser, **overrides) -> dict:
    """
    Switch the module on for the household.

    Defaults to `manual` so no deadline is derived from the household rule. The weekly
    default would put the cutoff before today for any meal in the near future, which
    would auto-close every meal these tests create.
    """

    payload = {
        "enabled": True,
        "deadlineMode": "manual",
        "autoLock": True,
        "reminderEnabled": False,
        "entryTypes": ["dinner"],
        **overrides,
    }
    response = api_client.put(api_routes.households_mealplan_attendance_settings, json=payload, headers=user.token)
    assert response.status_code == 200
    return response.json()


def create_recipe(user: TestUser, servings: float = 4) -> Recipe:
    return user.repos.recipes.create(
        Recipe(
            user_id=user.user_id,
            group_id=UUID(user.group_id),
            name=random_string(),
            recipe_servings=servings,
        )
    )


def create_dinner(user: TestUser, on: date, recipe: Recipe | None = None) -> int:
    entry = user.repos.meals.create(
        SavePlanEntry(
            date=on,
            entry_type="dinner",
            recipe_id=recipe.id if recipe else None,
            title="" if recipe else random_string(),
            group_id=UUID(user.group_id),
            user_id=user.user_id,
        )
    )
    return entry.id


def sync_participants(api_client: TestClient, user: TestUser) -> list[dict]:
    response = api_client.post(api_routes.households_mealplan_participants_sync, json={}, headers=user.token)
    assert response.status_code == 200
    return response.json()


def add_guest(api_client: TestClient, user: TestUser, parent_id: str, name: str | None = None) -> dict:
    response = api_client.post(
        api_routes.households_mealplan_participants,
        json={"name": name or random_string(), "parentId": parent_id, "defaultAttending": False},
        headers=user.token,
    )
    assert response.status_code == 201
    return response.json()


def get_meal(api_client: TestClient, user: TestUser, mealplan_id: int) -> dict:
    response = api_client.get(api_routes.households_mealplans_item_id_attendance(mealplan_id), headers=user.token)
    assert response.status_code == 200
    return response.json()


def answer(api_client: TestClient, user: TestUser, mealplan_id: int, participant_id: str, status: str):
    return api_client.put(
        api_routes.households_mealplans_item_id_attendance_participant_id(mealplan_id, participant_id),
        json={"status": status},
        headers=user.token,
    )


class MealPlanAttendanceSettingsTests:
    def test_settings_are_created_with_defaults_on_first_read(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        response = api_client.get(
            api_routes.households_mealplan_attendance_settings, headers=unique_user_fn_scoped.token
        )

        assert response.status_code == 200
        settings = response.json()
        # Off until somebody turns it on, and pre-set to the Thursday 20:00 rule.
        assert settings["enabled"] is False
        assert settings["deadlineMode"] == "weekly"
        assert settings["deadlineWeekday"] == 3
        assert settings["deadlineTime"].startswith("20:00")
        assert settings["entryTypes"] == ["dinner"]

    def test_settings_round_trip(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        settings = enable_attendance(
            api_client,
            unique_user_fn_scoped,
            deadlineMode="weekly",
            deadlineWeekday=3,
            deadlineTime="20:00:00",
            timezone="Europe/Berlin",
            entryTypes=["lunch", "dinner"],
        )

        assert settings["enabled"] is True
        assert settings["timezone"] == "Europe/Berlin"
        # Stored as a comma separated string, handed back as a list.
        assert settings["entryTypes"] == ["lunch", "dinner"]

    def test_invalid_timezone_is_rejected(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        response = api_client.put(
            api_routes.households_mealplan_attendance_settings,
            json={"enabled": True, "timezone": "Mars/Olympus_Mons"},
            headers=unique_user_fn_scoped.token,
        )

        assert response.status_code == 422


class MealPlanParticipantTests:
    def test_sync_creates_one_participant_per_household_member(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        participants = sync_participants(api_client, unique_user_fn_scoped)

        assert len(participants) == 1
        assert participants[0]["userId"] == str(unique_user_fn_scoped.user_id)
        # A household member eats along unless they say otherwise.
        assert participants[0]["defaultAttending"] is True

    def test_sync_is_idempotent(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        first = sync_participants(api_client, unique_user_fn_scoped)
        second = sync_participants(api_client, unique_user_fn_scoped)

        assert len(first) == len(second) == 1

    def test_guests_hang_off_the_person_they_belong_to(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        person = sync_participants(api_client, unique_user_fn_scoped)[0]
        guest = add_guest(api_client, unique_user_fn_scoped, person["id"], name="Partner")

        assert guest["parentId"] == person["id"]
        assert guest["userId"] is None
        # A partner is not assumed to be eating along.
        assert guest["defaultAttending"] is False


class MealPlanAttendanceOverviewTests:
    def test_defaults_are_applied_without_anybody_answering(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]
        add_guest(api_client, unique_user_fn_scoped, person["id"])

        recipe = create_recipe(unique_user_fn_scoped, servings=4)
        mealplan_id = create_dinner(unique_user_fn_scoped, today() + timedelta(days=2), recipe)

        meal = get_meal(api_client, unique_user_fn_scoped, mealplan_id)

        # The person defaults to yes, the guest to no, and neither has actually answered.
        assert meal["attendeeCount"] == 1
        assert meal["pendingResponseCount"] == 2
        assert all(attendee["hasResponded"] is False for attendee in meal["attendees"])
        assert meal["isLocked"] is False

    def test_confirmations_drive_the_scale_factor(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        """A recipe for four with a second person joining has to be scaled to 0.5x per head."""

        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]
        guest = add_guest(api_client, unique_user_fn_scoped, person["id"])

        recipe = create_recipe(unique_user_fn_scoped, servings=4)
        mealplan_id = create_dinner(unique_user_fn_scoped, today() + timedelta(days=2), recipe)

        response = answer(api_client, unique_user_fn_scoped, mealplan_id, guest["id"], "attending")
        assert response.status_code == 200

        meal = response.json()
        assert meal["attendeeCount"] == 2
        assert meal["servings"] == 2
        assert meal["recipeServings"] == 4
        assert meal["scaleFactor"] == 0.5

    def test_extra_guests_count_towards_the_portions(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]

        recipe = create_recipe(unique_user_fn_scoped, servings=4)
        mealplan_id = create_dinner(unique_user_fn_scoped, today() + timedelta(days=2), recipe)

        response = api_client.put(
            api_routes.households_mealplans_item_id_attendance_participant_id(mealplan_id, person["id"]),
            json={"status": "attending", "guestCount": 6},
            headers=unique_user_fn_scoped.token,
        )
        assert response.status_code == 200

        meal = response.json()
        # The brief's example: a recipe for four, seven people at the table.
        assert meal["attendeeCount"] == 7
        assert meal["scaleFactor"] == 1.75

    def test_a_manual_portion_count_wins_over_the_confirmations(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        enable_attendance(api_client, unique_user_fn_scoped)
        sync_participants(api_client, unique_user_fn_scoped)

        recipe = create_recipe(unique_user_fn_scoped, servings=4)
        mealplan_id = create_dinner(unique_user_fn_scoped, today() + timedelta(days=2), recipe)

        response = api_client.put(
            api_routes.households_mealplans_item_id_attendance_details(mealplan_id),
            json={"servingsOverride": 8},
            headers=unique_user_fn_scoped.token,
        )
        assert response.status_code == 200

        meal = response.json()
        assert meal["attendeeCount"] == 1
        assert meal["servings"] == 8
        assert meal["scaleFactor"] == 2

    def test_meal_types_outside_the_settings_are_ignored(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped, entryTypes=["lunch"])
        sync_participants(api_client, unique_user_fn_scoped)

        meal_date = today() + timedelta(days=2)
        create_dinner(unique_user_fn_scoped, meal_date)

        response = api_client.get(
            api_routes.households_mealplan_attendance,
            params={"start_date": meal_date.isoformat(), "end_date": meal_date.isoformat()},
            headers=unique_user_fn_scoped.token,
        )

        assert response.status_code == 200
        assert response.json()["meals"] == []


class MealPlanAbsenceTests:
    def test_an_absence_overrides_the_answer(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]

        meal_date = today() + timedelta(days=2)
        mealplan_id = create_dinner(unique_user_fn_scoped, meal_date, create_recipe(unique_user_fn_scoped))

        assert answer(api_client, unique_user_fn_scoped, mealplan_id, person["id"], "attending").status_code == 200

        response = api_client.post(
            api_routes.households_mealplan_absences,
            json={
                "participantId": person["id"],
                "startDate": meal_date.isoformat(),
                "endDate": (meal_date + timedelta(days=3)).isoformat(),
                "reason": "vacation",
            },
            headers=unique_user_fn_scoped.token,
        )
        assert response.status_code == 201

        meal = get_meal(api_client, unique_user_fn_scoped, mealplan_id)
        attendee = meal["attendees"][0]

        # Being away wins: somebody on holiday cannot eat along, whatever they clicked.
        assert attendee["isAbsent"] is True
        assert attendee["absenceReason"] == "vacation"
        assert attendee["status"] == "declined"
        assert meal["attendeeCount"] == 0

    def test_an_absence_outside_the_meal_date_changes_nothing(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]

        meal_date = today() + timedelta(days=2)
        mealplan_id = create_dinner(unique_user_fn_scoped, meal_date, create_recipe(unique_user_fn_scoped))

        api_client.post(
            api_routes.households_mealplan_absences,
            json={
                "participantId": person["id"],
                "startDate": (meal_date + timedelta(days=5)).isoformat(),
                "endDate": (meal_date + timedelta(days=8)).isoformat(),
                "reason": "business_trip",
            },
            headers=unique_user_fn_scoped.token,
        )

        meal = get_meal(api_client, unique_user_fn_scoped, mealplan_id)
        assert meal["attendees"][0]["isAbsent"] is False
        assert meal["attendeeCount"] == 1

    def test_end_before_start_is_rejected(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        person = sync_participants(api_client, unique_user_fn_scoped)[0]

        response = api_client.post(
            api_routes.households_mealplan_absences,
            json={
                "participantId": person["id"],
                "startDate": today().isoformat(),
                "endDate": (today() - timedelta(days=1)).isoformat(),
            },
            headers=unique_user_fn_scoped.token,
        )

        assert response.status_code == 422


class MealPlanLockingTests:
    def test_a_closed_meal_rejects_further_answers(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]
        mealplan_id = create_dinner(
            unique_user_fn_scoped, today() + timedelta(days=2), create_recipe(unique_user_fn_scoped)
        )

        response = api_client.post(
            api_routes.households_mealplans_item_id_attendance_lock(mealplan_id),
            json={},
            headers=unique_user_fn_scoped.token,
        )
        assert response.status_code == 200
        assert response.json()["isLocked"] is True

        blocked = answer(api_client, unique_user_fn_scoped, mealplan_id, person["id"], "declined")
        assert blocked.status_code == 423

    def test_closing_freezes_the_answers_that_were_only_defaults(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        """Nobody answered, so the defaults are what gets written down."""

        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]
        mealplan_id = create_dinner(
            unique_user_fn_scoped, today() + timedelta(days=2), create_recipe(unique_user_fn_scoped)
        )

        api_client.post(
            api_routes.households_mealplans_item_id_attendance_lock(mealplan_id),
            json={},
            headers=unique_user_fn_scoped.token,
        )

        # Changing the default afterwards must not rewrite a meal that is already closed.
        api_client.put(
            api_routes.households_mealplan_participants_item_id(person["id"]),
            json={**person, "defaultAttending": False},
            headers=unique_user_fn_scoped.token,
        )

        meal = get_meal(api_client, unique_user_fn_scoped, mealplan_id)
        assert meal["attendeeCount"] == 1
        assert meal["attendees"][0]["status"] == "attending"

    def test_reopening_makes_a_meal_writable_again(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]
        mealplan_id = create_dinner(
            unique_user_fn_scoped, today() + timedelta(days=2), create_recipe(unique_user_fn_scoped)
        )

        api_client.post(
            api_routes.households_mealplans_item_id_attendance_lock(mealplan_id),
            json={},
            headers=unique_user_fn_scoped.token,
        )

        response = api_client.post(
            api_routes.households_mealplans_item_id_attendance_unlock(mealplan_id),
            json={},
            headers=unique_user_fn_scoped.token,
        )
        assert response.status_code == 200

        meal = response.json()
        assert meal["isLocked"] is False
        # Reopening always sets a fresh deadline, otherwise the household rule would put the
        # cutoff back in the past and close the meal again on the next request.
        assert meal["deadlineAt"] is not None
        assert datetime.fromisoformat(meal["deadlineAt"]) > datetime.now(UTC)

        assert answer(api_client, unique_user_fn_scoped, mealplan_id, person["id"], "declined").status_code == 200

    def test_a_deadline_in_the_past_closes_the_meal(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped)
        person = sync_participants(api_client, unique_user_fn_scoped)[0]
        mealplan_id = create_dinner(
            unique_user_fn_scoped, today() + timedelta(days=2), create_recipe(unique_user_fn_scoped)
        )

        response = api_client.put(
            api_routes.households_mealplans_item_id_attendance_details(mealplan_id),
            json={"deadlineAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
            headers=unique_user_fn_scoped.token,
        )
        assert response.status_code == 200
        assert response.json()["deadlinePassed"] is True
        assert response.json()["isLocked"] is True

        assert answer(api_client, unique_user_fn_scoped, mealplan_id, person["id"], "declined").status_code == 423


class MealPlanAttendanceShoppingListTests:
    def test_only_closed_meals_are_added(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped)
        sync_participants(api_client, unique_user_fn_scoped)

        shopping_list = unique_user_fn_scoped.repos.group_shopping_lists.create(
            ShoppingListSave(
                name=random_string(10),
                group_id=unique_user_fn_scoped.group_id,
                user_id=unique_user_fn_scoped.user_id,
            )
        )

        meal_date = today() + timedelta(days=2)
        recipe = create_recipe(unique_user_fn_scoped, servings=4)
        mealplan_id = create_dinner(unique_user_fn_scoped, meal_date, recipe)

        payload = {
            "shoppingListId": str(shopping_list.id),
            "startDate": meal_date.isoformat(),
            "endDate": meal_date.isoformat(),
            "onlyLocked": True,
        }

        still_open = api_client.post(
            api_routes.households_mealplan_attendance_shopping_list, json=payload, headers=unique_user_fn_scoped.token
        )
        assert still_open.status_code == 200
        assert still_open.json()["added"] == []
        assert len(still_open.json()["skipped"]) == 1

        api_client.post(
            api_routes.households_mealplans_item_id_attendance_lock(mealplan_id),
            json={},
            headers=unique_user_fn_scoped.token,
        )

        closed = api_client.post(
            api_routes.households_mealplan_attendance_shopping_list, json=payload, headers=unique_user_fn_scoped.token
        )
        assert closed.status_code == 200

        added = closed.json()["added"]
        assert len(added) == 1
        assert added[0]["recipeId"] == str(recipe.id)
        # One confirmation against a recipe for four.
        assert added[0]["scaleFactor"] == 0.25

        updated_list = unique_user_fn_scoped.repos.group_shopping_lists.get_one(shopping_list.id)
        assert updated_list
        assert [ref.recipe_id for ref in updated_list.recipe_references] == [recipe.id]

    def test_meals_without_a_recipe_are_skipped(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        enable_attendance(api_client, unique_user_fn_scoped)
        sync_participants(api_client, unique_user_fn_scoped)

        shopping_list = unique_user_fn_scoped.repos.group_shopping_lists.create(
            ShoppingListSave(
                name=random_string(10),
                group_id=unique_user_fn_scoped.group_id,
                user_id=unique_user_fn_scoped.user_id,
            )
        )

        meal_date = today() + timedelta(days=2)
        create_dinner(unique_user_fn_scoped, meal_date)

        response = api_client.post(
            api_routes.households_mealplan_attendance_shopping_list,
            json={
                "shoppingListId": str(shopping_list.id),
                "startDate": meal_date.isoformat(),
                "endDate": meal_date.isoformat(),
                "onlyLocked": False,
            },
            headers=unique_user_fn_scoped.token,
        )

        assert response.status_code == 200
        assert response.json()["added"] == []
        assert "no recipe attached" in response.json()["skipped"][0]
