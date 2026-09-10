"""
The rolling plan: recipe suggestions and the algorithm that ranks them.

Three rules shape the ranking, all of them adjustable per request:

* favourites should come round more often,
* the same dish should rest for a few weeks before it reappears,
* and the same person should not end up deciding every time.
"""

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta

from pydantic import UUID4

from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan.attendance import (
    MealPlanRotationCandidate,
    MealPlanRotationProposal,
    MealPlanRotationRequest,
    MealPlanRotationSlot,
    MealPlanSuggestionOut,
    MealPlanSuggestionSave,
    MealPlanSuggestionUpdate,
    SuggestionStatus,
)
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.recipe.recipe import RecipeSummary

HISTORY_WINDOW_DAYS = 400
"""How far back the planner looks to work out cooldowns and who has been choosing."""

FAIRNESS_WINDOW_DAYS = 56
"""The recent stretch used to judge whether one person has been deciding too often."""


class _History:
    """One pass over the household's mealplan, reduced to what the scoring needs."""

    def __init__(self) -> None:
        self.upcoming: list[ReadPlanEntry] = []
        self.last_planned: dict[UUID4, date] = {}
        self.last_planner: dict[UUID4, UUID4 | None] = {}
        self.planner_counts: Counter[UUID4] = Counter()
        self.recipes: dict[UUID4, RecipeSummary] = {}


class MealPlanRotationService:
    def __init__(self, repos: AllRepositories) -> None:
        if not repos.group_id or not repos.household_id:
            raise ValueError("MealPlanRotationService requires group- and household-scoped repositories")

        self.repos = repos
        self.group_id: UUID4 = repos.group_id
        self.household_id: UUID4 = repos.household_id

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------

    def get_suggestions(self, status: SuggestionStatus | None = None) -> list[MealPlanSuggestionOut]:
        suggestions = self.repos.mealplan_suggestions.get_all(limit=None)
        if status:
            suggestions = [suggestion for suggestion in suggestions if suggestion.status == status]
        return suggestions

    def update_suggestion(self, data: MealPlanSuggestionUpdate) -> MealPlanSuggestionOut:
        existing = self.repos.mealplan_suggestions.get_one(data.id)
        if not existing:
            raise ValueError(f"suggestion {data.id} not found")

        return self.repos.mealplan_suggestions.update(
            data.id,
            MealPlanSuggestionSave(
                group_id=self.group_id,
                household_id=self.household_id,
                created_by_id=existing.created_by_id,
                recipe_id=existing.recipe_id,
                status=data.status,
                note=data.note,
            ),
        )

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def build_proposal(self, request: MealPlanRotationRequest) -> MealPlanRotationProposal:
        """Rank candidate recipes for every day in the range that has no meal of this type yet."""

        today = datetime.now(UTC).date()
        history = self._load_history(today, request.end_date)

        planned_dates = {
            (meal.date, meal.entry_type) for meal in history.upcoming if meal.entry_type == request.entry_type
        }
        already_planned_recipes = {meal.recipe_id for meal in history.upcoming if meal.recipe_id}

        candidates = self._score_candidates(request, history, already_planned_recipes, today)

        slots: list[MealPlanRotationSlot] = []
        current = request.start_date
        while current <= request.end_date:
            if (current, request.entry_type) not in planned_dates:
                slots.append(
                    MealPlanRotationSlot(
                        date=current, entry_type=request.entry_type, candidates=candidates[: request.limit]
                    )
                )
            current += timedelta(days=1)

        return MealPlanRotationProposal(cooldown_weeks=request.cooldown_weeks, slots=slots)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_history(self, today: date, horizon: date) -> _History:
        start = today - timedelta(days=HISTORY_WINDOW_DAYS)
        end = max(horizon, today)
        meals = self.repos.meals.get_meals_by_date_range(
            datetime.combine(start, time.min), datetime.combine(end, time.min)
        )

        history = _History()
        fairness_cutoff = today - timedelta(days=FAIRNESS_WINDOW_DAYS)

        for meal in sorted(meals, key=lambda m: m.date):
            if meal.date > today:
                history.upcoming.append(meal)
                continue

            if not meal.recipe_id:
                continue

            # Sorted ascending, so the last write wins and holds the most recent occurrence.
            history.last_planned[meal.recipe_id] = meal.date
            history.last_planner[meal.recipe_id] = meal.user_id
            if meal.date >= fairness_cutoff and meal.user_id:
                history.planner_counts[meal.user_id] += 1

            if meal.recipe:
                history.recipes[meal.recipe_id] = meal.recipe

        return history

    def _favorite_counts(self) -> dict[UUID4, int]:
        """How many members of the household have hearted each recipe."""

        counts: Counter = Counter()
        for user in self.repos.users.multi_query({"household_id": self.household_id}, limit=None):
            for rating in self.repos.user_ratings.get_by_user(user.id, favorites_only=True):
                counts[rating.recipe_id] += 1

        return dict(counts)

    def _score_candidates(
        self,
        request: MealPlanRotationRequest,
        history: _History,
        already_planned: set[UUID4],
        today: date,
    ) -> list[MealPlanRotationCandidate]:
        favorites = self._favorite_counts()
        open_suggestions = self.get_suggestions(SuggestionStatus.open)

        suggestion_counts: Counter = Counter()
        suggested_by: dict[UUID4, list[str]] = defaultdict(list)
        user_names = {
            user.id: (user.full_name or user.username or "")
            for user in self.repos.users.multi_query({"household_id": self.household_id}, limit=None)
        }

        for suggestion in open_suggestions:
            suggestion_counts[suggestion.recipe_id] += 1
            if suggestion.created_by_id:
                suggested_by[suggestion.recipe_id].append(user_names.get(suggestion.created_by_id, ""))
            if suggestion.recipe:
                history.recipes[suggestion.recipe_id] = suggestion.recipe

        candidate_ids = (set(favorites) | set(suggestion_counts) | set(history.last_planned)) - already_planned
        if not candidate_ids:
            return []

        missing = candidate_ids - set(history.recipes)
        for recipe in self.repos.recipes.get_summaries_by_ids(missing):
            if recipe.id:
                history.recipes[recipe.id] = recipe

        cooldown_days = request.cooldown_weeks * 7
        busiest_planner = history.planner_counts.most_common(1)
        dominant_planner = busiest_planner[0][0] if busiest_planner and busiest_planner[0][1] > 1 else None

        candidates: list[MealPlanRotationCandidate] = []
        for recipe_id in candidate_ids:
            recipe = history.recipes.get(recipe_id)
            if not recipe:
                continue

            last_planned = history.last_planned.get(recipe_id)
            days_since = (today - last_planned).days if last_planned else None

            if days_since is not None and days_since < cooldown_days:
                # Still resting -- the whole point of the cooldown.
                continue

            score = 1.0
            reasons: list[str] = []

            favorite_count = favorites.get(recipe_id, 0)
            if favorite_count:
                score += request.favorite_weight * favorite_count
                reasons.append(f"favourite of {favorite_count} member(s)")

            if suggestion_count := suggestion_counts.get(recipe_id, 0):
                score += request.suggestion_weight * suggestion_count
                reasons.append(f"suggested {suggestion_count} time(s)")

            if days_since is None:
                score += 0.5
                reasons.append("never planned before")
            else:
                # A gentle nudge for dishes that have been resting the longest.
                score += min(days_since / max(cooldown_days, 1), 3.0) - 1.0
                reasons.append(f"last cooked {days_since} days ago")

            last_planner = history.last_planner.get(recipe_id)
            if dominant_planner and last_planner == dominant_planner:
                score -= request.fairness_weight
                reasons.append("last picked by whoever has been choosing most")

            candidates.append(
                MealPlanRotationCandidate(
                    recipe=recipe,
                    score=round(score, 3),
                    last_planned_on=last_planned,
                    days_since_last=days_since,
                    favorite_count=favorite_count,
                    is_suggested=bool(suggestion_counts.get(recipe_id)),
                    suggested_by=[name for name in suggested_by.get(recipe_id, []) if name],
                    last_chosen_by=user_names.get(last_planner) if last_planner else None,
                    reasons=reasons,
                )
            )

        candidates.sort(key=lambda candidate: (-candidate.score, candidate.recipe.name or ""))
        return candidates
