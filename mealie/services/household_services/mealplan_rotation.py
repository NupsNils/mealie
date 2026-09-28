"""
The rolling plan: recipe suggestions and the algorithm that ranks them.

Three rules shape the ranking, all of them adjustable per request:

* favourites should come round more often,
* the same dish should rest for a few weeks before it reappears,
* and the same person should not end up deciding every time.

The last rule works in turns. Every open day belongs to whichever household member has had
the fewest picks lately, their wishes (hearts and suggestions) are pushed up for that day, and
the day counts as their pick. The next day therefore leans towards somebody else.
"""

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta

from pydantic import UUID4

from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan.attendance import (
    MealPlanRotationCandidate,
    MealPlanRotationPick,
    MealPlanRotationProposal,
    MealPlanRotationRequest,
    MealPlanRotationSlot,
    MealPlanSuggestionOut,
    MealPlanSuggestionSave,
    MealPlanSuggestionUpdate,
    SuggestionStatus,
)
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry, SavePlanEntry
from mealie.schema.recipe.recipe import RecipeSummary

HISTORY_WINDOW_DAYS = 400
"""How far back the planner looks to work out cooldowns and who has been choosing."""

FAIRNESS_WINDOW_DAYS = 56
"""The recent stretch used to judge whether one person has been deciding too often."""


class _History:
    """One pass over the household's mealplan, reduced to what the scoring needs."""

    def __init__(self) -> None:
        self.occupied: set[tuple[date, PlanEntryType]] = set()
        self.upcoming_recipes: set[UUID4] = set()
        self.last_planned: dict[UUID4, date] = {}
        self.last_planner: dict[UUID4, UUID4 | None] = {}
        self.planner_counts: Counter[UUID4] = Counter()
        """Meals each member put on the plan lately, including the ones still ahead."""

        self.last_pick: dict[UUID4, date] = {}
        self.recipes: dict[UUID4, RecipeSummary] = {}


class _Context:
    """Everything one proposal needs, plus the picks it has handed out so far."""

    def __init__(self, history: _History, members: dict[UUID4, str]) -> None:
        self.history = history
        self.members = members
        self.favorited_by: dict[UUID4, list[UUID4]] = defaultdict(list)
        self.suggested_by: dict[UUID4, list[UUID4 | None]] = defaultdict(list)
        self.picks: Counter[UUID4] = Counter(history.planner_counts)
        """Picks per member: the recent history plus the days handed out in this proposal."""

        self.last_pick: dict[UUID4, date] = dict(history.last_pick)
        self.taken: set[UUID4] = set(history.upcoming_recipes)
        """Recipes already on the plan ahead, or picked for an earlier day of this proposal."""

    def wishers(self, recipe_id: UUID4) -> set[UUID4]:
        return set(self.favorited_by.get(recipe_id, [])) | {
            user_id for user_id in self.suggested_by.get(recipe_id, []) if user_id
        }

    def names(self, user_ids: list[UUID4] | list[UUID4 | None]) -> list[str]:
        return [self.members[user_id] for user_id in user_ids if user_id and self.members.get(user_id)]

    def next_decider(self) -> UUID4 | None:
        """
        The member with the fewest picks. A tie goes to whoever picked least recently, so a
        new week does not always start with the same person, and then by name to stay stable.
        """

        if not self.members:
            return None
        return min(
            self.members,
            key=lambda user_id: (self.picks[user_id], self.last_pick.get(user_id, date.min), self.members[user_id]),
        )

    def record_pick(self, user_id: UUID4, day: date) -> None:
        self.picks[user_id] += 1
        self.last_pick[user_id] = max(day, self.last_pick.get(user_id, date.min))

    def busiest_decider(self) -> UUID4 | None:
        busiest = self.picks.most_common(1)
        return busiest[0][0] if busiest and busiest[0][1] > 1 else None


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
        """
        Rank candidate recipes for every day in the range that has no meal of this type yet.

        The days are worked through in order as if each got its top candidate: that recipe is
        not offered again for a later day, and the day counts as a pick for whoever's turn it
        was, so the next day leans towards somebody else's wishes.
        """

        today = datetime.now(UTC).date()
        context = self._load_context(today, request.end_date)

        slots: list[MealPlanRotationSlot] = []
        current = max(request.start_date, today)
        while current <= request.end_date:
            if (current, request.entry_type) not in context.history.occupied:
                decider = context.next_decider()
                candidates = self._score_candidates(request, context, current, today, decider)

                slots.append(
                    MealPlanRotationSlot(
                        date=current,
                        entry_type=request.entry_type,
                        decider_id=decider,
                        decider=context.members.get(decider) if decider else None,
                        candidates=candidates[: request.limit],
                    )
                )

                if candidates and candidates[0].recipe.id:
                    context.taken.add(candidates[0].recipe.id)
                    if decider:
                        context.record_pick(decider, current)

            current += timedelta(days=1)

        return MealPlanRotationProposal(cooldown_weeks=request.cooldown_weeks, slots=slots)

    def fill(self, request: MealPlanRotationRequest) -> list[ReadPlanEntry]:
        """
        Put the top candidate of every open day in the range on the meal plan.

        Each meal is recorded as chosen by whoever's turn the day was, which is what the
        fairness rule reads back the next time round.
        """

        created: list[ReadPlanEntry] = []
        for slot in self.build_proposal(request).slots:
            if not slot.candidates or not slot.decider_id or not slot.candidates[0].recipe.id:
                continue
            created.append(self._plan(slot.date, slot.entry_type, slot.candidates[0].recipe.id, slot.decider_id))

        return created

    def plan_pick(self, pick: MealPlanRotationPick, user_id: UUID4) -> ReadPlanEntry:
        """Put one recipe on the meal plan, chosen by hand by `user_id`."""

        if not self.repos.recipes.get_one(pick.recipe_id, "id"):
            raise ValueError(f"recipe {pick.recipe_id} not found")

        return self._plan(pick.date, pick.entry_type, pick.recipe_id, user_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _plan(self, day: date, entry_type: PlanEntryType, recipe_id: UUID4, user_id: UUID4) -> ReadPlanEntry:
        entry = self.repos.meals.create(
            SavePlanEntry(
                date=day,
                entry_type=entry_type,
                recipe_id=recipe_id,
                group_id=self.group_id,
                user_id=user_id,
            )
        )

        # A suggestion has done its job once the recipe is on the plan.
        for suggestion in self.get_suggestions(SuggestionStatus.open):
            if suggestion.recipe_id == recipe_id:
                self.update_suggestion(
                    MealPlanSuggestionUpdate(id=suggestion.id, status=SuggestionStatus.planned, note=suggestion.note)
                )

        return entry

    def _load_history(self, today: date, horizon: date) -> _History:
        start = today - timedelta(days=HISTORY_WINDOW_DAYS)
        end = max(horizon, today)
        meals = self.repos.meals.get_meals_by_date_range(
            datetime.combine(start, time.min), datetime.combine(end, time.min)
        )

        history = _History()
        fairness_cutoff = today - timedelta(days=FAIRNESS_WINDOW_DAYS)

        for meal in sorted(meals, key=lambda m: m.date):
            history.occupied.add((meal.date, meal.entry_type))

            # A meal already on the plan ahead was somebody's pick too, so a new round
            # carries on from where the last one left off instead of starting over.
            if meal.recipe_id and meal.user_id and meal.date >= fairness_cutoff:
                history.planner_counts[meal.user_id] += 1
                history.last_pick[meal.user_id] = meal.date

            if meal.date > today:
                if meal.recipe_id:
                    history.upcoming_recipes.add(meal.recipe_id)
                continue

            if not meal.recipe_id:
                continue

            # Sorted ascending, so the last write wins and holds the most recent occurrence.
            history.last_planned[meal.recipe_id] = meal.date
            history.last_planner[meal.recipe_id] = meal.user_id

            if meal.recipe:
                history.recipes[meal.recipe_id] = meal.recipe

        return history

    def _load_context(self, today: date, horizon: date) -> _Context:
        users = self.repos.users.multi_query({"household_id": self.household_id}, limit=None)
        members = {user.id: (user.full_name or user.username or "") for user in users}
        context = _Context(self._load_history(today, horizon), members)

        # Only members count: a pick recorded for somebody who has since left stays in the
        # history for cooldowns, but should not make anyone look busier or quieter.
        context.picks = Counter({user_id: count for user_id, count in context.picks.items() if user_id in members})

        for user in users:
            for rating in self.repos.user_ratings.get_by_user(user.id, favorites_only=True):
                context.favorited_by[rating.recipe_id].append(user.id)

        for suggestion in self.get_suggestions(SuggestionStatus.open):
            context.suggested_by[suggestion.recipe_id].append(suggestion.created_by_id)
            if suggestion.recipe:
                context.history.recipes[suggestion.recipe_id] = suggestion.recipe

        return context

    def _score_candidates(
        self,
        request: MealPlanRotationRequest,
        context: _Context,
        day: date,
        today: date,
        decider: UUID4 | None,
    ) -> list[MealPlanRotationCandidate]:
        history = context.history
        candidate_ids = (
            set(context.favorited_by) | set(context.suggested_by) | set(history.last_planned)
        ) - context.taken
        if not candidate_ids:
            return []

        missing = candidate_ids - set(history.recipes)
        if missing:
            for recipe in self.repos.recipes.get_summaries_by_ids(missing):
                if recipe.id:
                    history.recipes[recipe.id] = recipe

        cooldown_days = request.cooldown_weeks * 7
        busiest = context.busiest_decider()

        candidates: list[MealPlanRotationCandidate] = []
        for recipe_id in candidate_ids:
            recipe = history.recipes.get(recipe_id)
            if not recipe:
                continue

            last_planned = history.last_planned.get(recipe_id)
            # The rest is counted up to the day being planned, not up to today.
            if last_planned and (day - last_planned).days < cooldown_days:
                continue

            days_since = (today - last_planned).days if last_planned else None
            score = 1.0
            reasons: list[str] = []

            favorited_by = context.favorited_by.get(recipe_id, [])
            if favorited_by:
                score += request.favorite_weight * len(favorited_by)
                reasons.append(f"favourite of {len(favorited_by)} member(s)")

            if suggestion_count := len(context.suggested_by.get(recipe_id, [])):
                score += request.suggestion_weight * suggestion_count
                reasons.append(f"suggested {suggestion_count} time(s)")

            if last_planned is None:
                score += 0.5
                reasons.append("never planned before")
            else:
                # A gentle nudge for dishes that have been resting the longest.
                score += min((day - last_planned).days / max(cooldown_days, 1), 3.0) - 1.0
                reasons.append(f"last cooked {days_since} days ago")

            wish_of_decider = bool(decider and decider in context.wishers(recipe_id))
            if wish_of_decider:
                score += request.fairness_weight
                reasons.append("wished for by whoever's turn it is")

            last_planner = history.last_planner.get(recipe_id)
            chosen_by_busiest = bool(busiest and last_planner == busiest)
            if chosen_by_busiest:
                score -= request.fairness_weight
                reasons.append("last picked by whoever has been choosing most")

            candidates.append(
                MealPlanRotationCandidate(
                    recipe=recipe,
                    score=round(score, 3),
                    last_planned_on=last_planned,
                    days_since_last=days_since,
                    favorite_count=len(favorited_by),
                    favorited_by=context.names(favorited_by),
                    is_suggested=bool(suggestion_count),
                    suggested_by=context.names(context.suggested_by.get(recipe_id, [])),
                    last_chosen_by=context.members.get(last_planner) if last_planner else None,
                    wish_of_decider=wish_of_decider,
                    chosen_by_busiest=chosen_by_busiest,
                    reasons=reasons,
                )
            )

        candidates.sort(key=lambda candidate: (-candidate.score, candidate.recipe.name or ""))
        return candidates
