from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from mealie.schema.meal_plan.new_meal import SavePlanEntry
from mealie.schema.recipe.recipe import Recipe
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

    def test_a_recipe_inside_its_cooldown_is_held_back(
        self, api_client: TestClient, unique_user_fn_scoped: TestUser
    ):
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
