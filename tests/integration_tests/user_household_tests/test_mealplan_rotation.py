from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from mealie.schema.meal_plan.new_meal import SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.services.household_services.mealplan_attendance import MealPlanAttendanceService
from mealie.services.scheduler.tasks.mealplan_attendance import auto_plan
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def today() -> date:
    return datetime.now(UTC).date()


def create_recipe(user: TestUser, name: str | None = None) -> Recipe:
    return user.repos.recipes.create(
        Recipe(user_id=user.user_id, group_id=UUID(user.group_id), name=name or random_string())
    )


def plan_dinner(user: TestUser, on: date, recipe: Recipe) -> int:
    return user.repos.meals.create(
        SavePlanEntry(
            date=on,
            entry_type="dinner",
            recipe_id=recipe.id,
            group_id=UUID(user.group_id),
            user_id=user.user_id,
        )
    ).id


def rotation(api_client: TestClient, user: TestUser, **overrides) -> dict:
    slot_day = today() + timedelta(days=10)
    payload = {
        "startDate": slot_day.isoformat(),
        "endDate": slot_day.isoformat(),
        "entryType": "dinner",
        "cooldownWeeks": 6,
        **overrides,
    }
    response = api_client.post(api_routes.households_mealplan_suggestions_rotation, json=payload, headers=user.token)
    assert response.status_code == 200
    return response.json()


def candidate_names(proposal: dict) -> list[str]:
    slots = proposal["slots"]
    assert len(slots) == 1
    return [candidate["recipe"]["name"] for candidate in slots[0]["candidates"]]


class MealPlanSuggestionTests:
    def test_anyone_can_propose_a_recipe(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        recipe = create_recipe(unique_user_fn_scoped)

        response = api_client.post(
            api_routes.households_mealplan_suggestions,
            json={"recipeId": str(recipe.id), "note": "the kids ask for this one"},
            headers=unique_user_fn_scoped.token,
        )

        assert response.status_code == 201
        suggestion = response.json()
        assert suggestion["recipeId"] == str(recipe.id)
        assert suggestion["status"] == "open"
        assert suggestion["createdById"] == str(unique_user_fn_scoped.user_id)

    def test_the_same_recipe_cannot_be_proposed_twice_by_one_person(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        recipe = create_recipe(unique_user_fn_scoped)
        body = {"recipeId": str(recipe.id)}

        assert (
            api_client.post(
                api_routes.households_mealplan_suggestions, json=body, headers=unique_user_fn_scoped.token
            ).status_code
            == 201
        )
        duplicate = api_client.post(
            api_routes.households_mealplan_suggestions, json=body, headers=unique_user_fn_scoped.token
        )

        assert duplicate.status_code == 409

    def test_a_suggestion_can_be_withdrawn(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        recipe = create_recipe(unique_user_fn_scoped)
        created = api_client.post(
            api_routes.households_mealplan_suggestions,
            json={"recipeId": str(recipe.id)},
            headers=unique_user_fn_scoped.token,
        ).json()

        deleted = api_client.delete(
            api_routes.households_mealplan_suggestions_item_id(created["id"]), headers=unique_user_fn_scoped.token
        )
        assert deleted.status_code == 200

        remaining = api_client.get(
            api_routes.households_mealplan_suggestions, headers=unique_user_fn_scoped.token
        ).json()
        assert remaining["items"] == []


class MealPlanRotationTests:
    def test_a_suggested_recipe_is_proposed(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        recipe = create_recipe(unique_user_fn_scoped, name="Suggested Dish")
        api_client.post(
            api_routes.households_mealplan_suggestions,
            json={"recipeId": str(recipe.id)},
            headers=unique_user_fn_scoped.token,
        )

        proposal = rotation(api_client, unique_user_fn_scoped)
        slot = proposal["slots"][0]
        candidate = slot["candidates"][0]

        assert candidate["recipe"]["name"] == "Suggested Dish"
        assert candidate["isSuggested"] is True
        assert candidate["daysSinceLast"] is None
        # The score is explained rather than just asserted.
        assert any("suggested" in reason for reason in candidate["reasons"])

    def test_a_recipe_inside_its_cooldown_is_held_back(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        recent = create_recipe(unique_user_fn_scoped, name="Cooked Last Week")
        plan_dinner(unique_user_fn_scoped, today() - timedelta(days=7), recent)

        held_back = rotation(api_client, unique_user_fn_scoped, cooldownWeeks=6)
        assert "Cooked Last Week" not in candidate_names(held_back)

        # With no cooldown the same recipe is fair game again.
        allowed = rotation(api_client, unique_user_fn_scoped, cooldownWeeks=0)
        assert "Cooked Last Week" in candidate_names(allowed)

    def test_a_recipe_past_its_cooldown_comes_round_again(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        rested = create_recipe(unique_user_fn_scoped, name="Long Ago")
        plan_dinner(unique_user_fn_scoped, today() - timedelta(days=90), rested)

        proposal = rotation(api_client, unique_user_fn_scoped, cooldownWeeks=6)
        names = candidate_names(proposal)

        assert "Long Ago" in names
        candidate = proposal["slots"][0]["candidates"][names.index("Long Ago")]
        assert candidate["daysSinceLast"] == 90

    def test_days_that_already_have_a_meal_are_not_offered(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        recipe = create_recipe(unique_user_fn_scoped)
        api_client.post(
            api_routes.households_mealplan_suggestions,
            json={"recipeId": str(recipe.id)},
            headers=unique_user_fn_scoped.token,
        )

        slot_day = today() + timedelta(days=10)
        plan_dinner(unique_user_fn_scoped, slot_day, create_recipe(unique_user_fn_scoped))

        proposal = rotation(api_client, unique_user_fn_scoped)
        assert proposal["slots"] == []

    def test_an_already_planned_recipe_is_not_proposed_again(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        recipe = create_recipe(unique_user_fn_scoped, name="Already On The Plan")
        api_client.post(
            api_routes.households_mealplan_suggestions,
            json={"recipeId": str(recipe.id)},
            headers=unique_user_fn_scoped.token,
        )
        # Planned for a different day in the future, so it should not fill another slot too.
        plan_dinner(unique_user_fn_scoped, today() + timedelta(days=3), recipe)

        proposal = rotation(api_client, unique_user_fn_scoped)
        assert "Already On The Plan" not in candidate_names(proposal)

    def test_end_before_start_is_rejected(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        response = api_client.post(
            api_routes.households_mealplan_suggestions_rotation,
            json={
                "startDate": today().isoformat(),
                "endDate": (today() - timedelta(days=1)).isoformat(),
            },
            headers=unique_user_fn_scoped.token,
        )

        assert response.status_code == 400

    def test_the_days_take_turns_between_everyones_wishes(self, api_client: TestClient, user_tuple: list[TestUser]):
        """Nobody has picked lately, so the two days go to one member each, and each gets their own wish."""

        first, second = user_tuple
        wishes = {}
        for user in (first, second):
            recipe = create_recipe(user)
            suggest(api_client, user, recipe)
            wishes[user.user_id] = recipe.name

        start = today() + timedelta(days=20)
        proposal = rotation(
            api_client, first, startDate=start.isoformat(), endDate=(start + timedelta(days=1)).isoformat()
        )

        slots = proposal["slots"]
        assert len(slots) == 2
        assert {slot["deciderId"] for slot in slots} == {str(first.user_id), str(second.user_id)}
        for slot in slots:
            top = slot["candidates"][0]
            assert top["wishOfDecider"] is True
            assert top["recipe"]["name"] == wishes[UUID(slot["deciderId"])]

    def test_a_meal_already_planned_ahead_counts_as_a_pick(self, api_client: TestClient, user_tuple: list[TestUser]):
        """Otherwise every new round would start with the same person again."""

        first, second = user_tuple
        # Whoever would win the tie by name gets a meal ahead, so the other one must go first.
        ahead = min(user_tuple, key=lambda user: user.full_name)
        other = second if ahead is first else first

        mealplan_id = plan_dinner(ahead, today() + timedelta(days=30), create_recipe(ahead))
        try:
            start = today() + timedelta(days=40)
            proposal = rotation(api_client, first, startDate=start.isoformat(), endDate=start.isoformat())
            assert proposal["slots"][0]["deciderId"] == str(other.user_id)
        finally:
            ahead.repos.meals.delete(mealplan_id)


def suggest(api_client: TestClient, user: TestUser, recipe: Recipe) -> dict:
    response = api_client.post(
        api_routes.households_mealplan_suggestions, json={"recipeId": str(recipe.id)}, headers=user.token
    )
    assert response.status_code == 201
    return response.json()


class MealPlanRotationPlanningTests:
    def test_fill_puts_a_different_top_pick_on_every_open_day(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        user = unique_user_fn_scoped
        recipes = [create_recipe(user, name=name) for name in ("Lasagne", "Chili")]
        for recipe in recipes:
            suggest(api_client, user, recipe)
        names = {recipe.name for recipe in recipes}

        start = today() + timedelta(days=10)
        payload = {
            "startDate": start.isoformat(),
            "endDate": (start + timedelta(days=1)).isoformat(),
            "entryType": "dinner",
        }
        response = api_client.post(
            api_routes.households_mealplan_suggestions_rotation_fill, json=payload, headers=user.token
        )

        assert response.status_code == 201
        planned = response.json()
        assert {entry["recipe"]["name"] for entry in planned} == names
        assert {entry["date"] for entry in planned} == {start.isoformat(), (start + timedelta(days=1)).isoformat()}

        # Both days are taken now, and the suggestions have done their job.
        assert rotation(api_client, user, **payload)["slots"] == []
        suggestions = api_client.get(api_routes.households_mealplan_suggestions, headers=user.token).json()["items"]
        assert {suggestion["status"] for suggestion in suggestions} == {"planned"}

    def test_a_candidate_can_be_planned_by_hand(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        user = unique_user_fn_scoped
        recipe = create_recipe(user)
        suggest(api_client, user, recipe)

        day = today() + timedelta(days=5)
        response = api_client.post(
            api_routes.households_mealplan_suggestions_rotation_plan,
            json={"date": day.isoformat(), "entryType": "dinner", "recipeId": str(recipe.id)},
            headers=user.token,
        )

        assert response.status_code == 201
        entry = response.json()
        assert entry["recipeId"] == str(recipe.id)
        assert entry["userId"] == str(user.user_id)
        suggestions = api_client.get(api_routes.households_mealplan_suggestions, headers=user.token).json()["items"]
        assert suggestions[0]["status"] == "planned"

    def test_planning_an_unknown_recipe_is_rejected(self, api_client: TestClient, unique_user_fn_scoped: TestUser):
        response = api_client.post(
            api_routes.households_mealplan_suggestions_rotation_plan,
            json={"date": today().isoformat(), "recipeId": str(uuid4())},
            headers=unique_user_fn_scoped.token,
        )

        assert response.status_code == 404

    def test_the_weekly_auto_plan_runs_once_on_its_weekday(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
        user = unique_user_fn_scoped
        weekday = datetime.now(UTC).weekday()
        response = api_client.put(
            api_routes.households_mealplan_attendance_settings,
            json={
                "enabled": True,
                "deadlineMode": "manual",
                "timezone": "UTC",
                "entryTypes": ["dinner"],
                "autoPlanEnabled": True,
                "autoPlanWeekday": weekday,
                "autoPlanDays": 3,
            },
            headers=user.token,
        )
        assert response.status_code == 200
        suggest(api_client, user, create_recipe(user, name="Auto Planned"))

        service = MealPlanAttendanceService(user.repos)
        assert service.auto_plan_window(datetime.now(UTC) + timedelta(days=1)) is None  # wrong weekday

        # One candidate for three days: the first day gets it, the other two stay empty.
        assert auto_plan(user.repos, service) == 1
        planned = user.repos.meals.get_meals_by_date_range(
            datetime.now(UTC) + timedelta(days=1), datetime.now(UTC) + timedelta(days=3)
        )
        assert [meal.recipe.name for meal in planned if meal.recipe] == ["Auto Planned"]

        # Already ran today, so it waits for next week.
        assert auto_plan(user.repos, MealPlanAttendanceService(user.repos)) == 0
