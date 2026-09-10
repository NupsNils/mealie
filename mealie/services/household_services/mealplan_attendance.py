"""
Business logic for the meal attendance module.

Reads never write. The summaries a client sees are projected on the fly from the
participants, their defaults, their absences and whatever answers have actually been
stored. Rows are only persisted when somebody answers, when a meal is locked (which
freezes the projection into real rows), or when per-meal details such as a deadline
override or the cook are set.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from functools import cached_property
from typing import NamedTuple
from zoneinfo import ZoneInfo

from pydantic import UUID4

from mealie.repos.repository_factory import AllRepositories
from mealie.schema.household.group_shopping_list import ShoppingListAddRecipeParamsBulk
from mealie.schema.meal_plan.attendance import (
    AttendanceStatus,
    DeadlineMode,
    MealPlanAbsenceOut,
    MealPlanAttendanceBulkUpdate,
    MealPlanAttendanceOut,
    MealPlanAttendanceOverview,
    MealPlanAttendanceSave,
    MealPlanAttendanceSettingsOut,
    MealPlanAttendanceSettingsSave,
    MealPlanAttendanceSettingsUpdate,
    MealPlanAttendanceShoppingListEntry,
    MealPlanAttendanceShoppingListRequest,
    MealPlanAttendanceShoppingListResult,
    MealPlanAttendanceSummary,
    MealPlanAttendanceUpdate,
    MealPlanAttendeeSummary,
    MealPlanEntryDetailsOut,
    MealPlanEntryDetailsSave,
    MealPlanEntryDetailsUpdate,
    MealPlanParticipantOut,
    MealPlanParticipantSave,
)
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry

from .shopping_lists import ShoppingListService

DEFAULT_REOPEN_WINDOW = timedelta(hours=24)
"""How long a meal stays open when it is unlocked without an explicit new deadline."""

LOCK_LOOKAHEAD_DAYS = 60
"""How far ahead the scheduler looks for meals whose deadline has passed."""


def compute_deadline_for(settings: MealPlanAttendanceSettingsUpdate, meal_date: date) -> datetime | None:
    """
    Derive the cutoff for a meal from a household's settings.

    `weekly` picks the last occurrence of the configured weekday strictly before the
    meal's day, so every meal between two cutoffs shares one deadline: with a Thursday
    20:00 rule, the Sunday, Monday and Tuesday of the following week all close at the
    same moment. `relative` counts a fixed number of days back from the meal itself, and
    `manual` leaves the meal without an automatic deadline.
    """

    if settings.deadline_mode == DeadlineMode.manual:
        return None

    if settings.deadline_mode == DeadlineMode.relative:
        cutoff_day = meal_date - timedelta(days=settings.deadline_lead_days)
    else:
        days_back = (meal_date.weekday() - settings.deadline_weekday) % 7 or 7
        cutoff_day = meal_date - timedelta(days=days_back)

    local = datetime.combine(cutoff_day, settings.deadline_time, tzinfo=ZoneInfo(settings.timezone))
    return local.astimezone(UTC)


def compute_scale_factor(servings: float, recipe_servings: float) -> float:
    """
    How far the recipe has to be scaled to feed everyone who confirmed.

    A recipe for four with seven confirmations gives 1.75. Recipes that do not declare a
    yield are left alone, since there is nothing to scale relative to.
    """

    if recipe_servings <= 0 or servings <= 0:
        return 1.0
    return servings / recipe_servings


class _SummaryContext(NamedTuple):
    """Everything one pass over a date range produced, so callers do not requery."""

    summaries: list[MealPlanAttendanceSummary]
    participants: list[MealPlanParticipantOut]
    absences: list[MealPlanAbsenceOut]
    details: dict[int, MealPlanEntryDetailsOut]


class MealPlanAttendanceError(Exception):
    """Raised for rule violations the API turns into 4xx responses."""


class MealPlanLockedError(MealPlanAttendanceError):
    """The meal's deadline has passed, so its attendance can no longer change."""


class MealPlanAttendanceService:
    def __init__(self, repos: AllRepositories) -> None:
        if not repos.group_id or not repos.household_id:
            raise ValueError("MealPlanAttendanceService requires group- and household-scoped repositories")

        self.repos = repos
        self.group_id: UUID4 = repos.group_id
        self.household_id: UUID4 = repos.household_id

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @cached_property
    def settings(self) -> MealPlanAttendanceSettingsOut:
        """The household's settings, created with defaults the first time they are needed."""

        existing = self.repos.mealplan_attendance_settings.get_one(self.household_id, key="household_id")
        if existing:
            return existing

        defaults = MealPlanAttendanceSettingsSave(group_id=self.group_id, household_id=self.household_id)
        return self.repos.mealplan_attendance_settings.create(defaults.to_db_values())

    def update_settings(self, data: MealPlanAttendanceSettingsUpdate) -> MealPlanAttendanceSettingsOut:
        # Touch the property first so a household updating its settings before ever reading
        # them still has a row to update.
        _ = self.settings

        save = MealPlanAttendanceSettingsSave(
            **data.model_dump(), group_id=self.group_id, household_id=self.household_id
        )
        # This repository is keyed on household_id, not on the row's own id.
        updated = self.repos.mealplan_attendance_settings.update(self.household_id, save.to_db_values())

        self.__dict__["settings"] = updated
        return updated

    @property
    def _relevant_entry_types(self) -> set[PlanEntryType]:
        return set(self.settings.entry_types)

    # ------------------------------------------------------------------
    # Participants
    # ------------------------------------------------------------------

    def get_participants(self) -> list[MealPlanParticipantOut]:
        return self.repos.mealplan_participants.get_active()

    def sync_participants_from_users(self) -> list[MealPlanParticipantOut]:
        """
        Make sure every user in the household has a participant row.

        Called whenever the module is opened so a freshly enabled household starts with
        a sensible roster instead of an empty table.
        """

        existing = self.repos.mealplan_participants.get_all(limit=None)
        linked_user_ids = {p.user_id for p in existing if p.user_id}

        household_users = self.repos.users.multi_query({"household_id": self.household_id}, limit=None)
        missing = [user for user in household_users if user.id not in linked_user_ids]

        if missing:
            self.repos.mealplan_participants.create_many(
                [
                    MealPlanParticipantSave(
                        group_id=self.group_id,
                        household_id=self.household_id,
                        user_id=user.id,
                        name=user.full_name or user.username or "",
                        default_attending=True,
                    ).model_dump()
                    for user in missing
                ]
            )

        return self.get_participants()

    # ------------------------------------------------------------------
    # Deadlines
    # ------------------------------------------------------------------

    def compute_deadline(self, meal_date: date) -> datetime | None:
        return compute_deadline_for(self.settings, meal_date)

    def effective_deadline(self, meal_date: date, details: MealPlanEntryDetailsOut | None) -> datetime | None:
        """A per-meal override always wins over the household rule."""

        if details and details.deadline_at:
            return details.deadline_at
        return self.compute_deadline(meal_date)

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------

    @staticmethod
    def _default_status(participant: MealPlanParticipantOut) -> AttendanceStatus:
        return AttendanceStatus.attending if participant.default_attending else AttendanceStatus.declined

    @staticmethod
    def _absence_for(
        absences: list[MealPlanAbsenceOut], participant_id: UUID4, meal_date: date
    ) -> MealPlanAbsenceOut | None:
        for absence in absences:
            if absence.participant_id == participant_id and absence.start_date <= meal_date <= absence.end_date:
                return absence
        return None

    def _build_attendee(
        self,
        participant: MealPlanParticipantOut,
        stored: MealPlanAttendanceOut | None,
        absence: MealPlanAbsenceOut | None,
    ) -> MealPlanAttendeeSummary:
        status = stored.status if stored else self._default_status(participant)
        guest_count = stored.guest_count if stored else 0

        if absence:
            # An absence is authoritative: somebody who is away cannot eat along.
            status = AttendanceStatus.declined
            guest_count = 0

        return MealPlanAttendeeSummary(
            participant_id=participant.id,
            participant_name=participant.name,
            user_id=participant.user_id,
            parent_id=participant.parent_id,
            is_guest=participant.user_id is None,
            status=status,
            guest_count=guest_count,
            note=stored.note if stored else None,
            has_responded=bool(stored and stored.responded_at),
            is_absent=absence is not None,
            absence_reason=absence.reason if absence else None,
        )

    def _build_summary(
        self,
        meal: ReadPlanEntry,
        participants: list[MealPlanParticipantOut],
        stored_by_participant: dict[UUID4, MealPlanAttendanceOut],
        absences: list[MealPlanAbsenceOut],
        details: MealPlanEntryDetailsOut | None,
        now: datetime,
    ) -> MealPlanAttendanceSummary:
        attendees = [
            self._build_attendee(
                participant,
                stored_by_participant.get(participant.id),
                self._absence_for(absences, participant.id, meal.date),
            )
            for participant in participants
        ]

        attendee_count = sum(
            1 + attendee.guest_count for attendee in attendees if attendee.status == AttendanceStatus.attending
        )
        pending = sum(1 for attendee in attendees if not attendee.has_responded and not attendee.is_absent)

        deadline = self.effective_deadline(meal.date, details)
        deadline_passed = bool(deadline and now >= deadline)
        is_locked = bool(details and details.locked) or (self.settings.auto_lock and deadline_passed)

        servings_override = details.servings_override if details else None
        servings = servings_override if servings_override is not None else float(attendee_count)

        recipe_servings = 0.0
        if meal.recipe:
            recipe_servings = meal.recipe.recipe_servings or meal.recipe.recipe_yield_quantity or 0.0

        scale_factor = compute_scale_factor(servings, recipe_servings)

        return MealPlanAttendanceSummary(
            mealplan_id=meal.id,
            date=meal.date,
            entry_type=meal.entry_type,
            title=meal.title,
            recipe_id=meal.recipe_id,
            recipe_name=meal.recipe.name if meal.recipe else None,
            recipe_slug=meal.recipe.slug if meal.recipe else None,
            deadline_at=deadline,
            is_locked=is_locked,
            deadline_passed=deadline_passed,
            attendee_count=attendee_count,
            pending_response_count=pending,
            servings=servings,
            servings_override=servings_override,
            recipe_servings=recipe_servings,
            scale_factor=scale_factor,
            cook_participant_id=details.cook_participant_id if details else None,
            shopper_participant_id=details.shopper_participant_id if details else None,
            attendees=attendees,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _get_meals(self, start_date: date, end_date: date) -> list[ReadPlanEntry]:
        meals = self.repos.meals.get_meals_by_date_range(
            datetime.combine(start_date, time.min), datetime.combine(end_date, time.min)
        )
        relevant = self._relevant_entry_types
        return sorted(
            (meal for meal in meals if meal.entry_type in relevant), key=lambda m: (m.date, m.entry_type.value)
        )

    def _resolve_participants(self, stored: list[MealPlanAttendanceOut]) -> list[MealPlanParticipantOut]:
        """
        Active participants, plus anyone inactive who already has an answer on record.

        Without the second half, retiring a participant would silently erase them from
        meals that were already locked with their answer in them.
        """

        participants = self.get_participants()
        known = {participant.id for participant in participants}
        missing = {record.participant_id for record in stored} - known
        if not missing:
            return participants

        archived = [
            participant
            for participant in self.repos.mealplan_participants.get_all(limit=None)
            if participant.id in missing
        ]
        return participants + sorted(archived, key=lambda p: p.name)

    def _summaries_for(
        self, meals: list[ReadPlanEntry], start_date: date, end_date: date, now: datetime | None = None
    ) -> "_SummaryContext":
        now = now or datetime.now(UTC)
        absences = self.repos.mealplan_absences.get_overlapping(start_date, end_date)

        mealplan_ids = [meal.id for meal in meals]
        details_by_meal = {
            d.mealplan_id: d for d in self.repos.mealplan_entry_details.get_by_mealplan_ids(mealplan_ids)
        }

        stored_records = self.repos.mealplan_attendance.get_by_mealplan_ids(mealplan_ids)
        stored_by_meal: dict[int, dict[UUID4, MealPlanAttendanceOut]] = defaultdict(dict)
        for record in stored_records:
            stored_by_meal[record.mealplan_id][record.participant_id] = record

        participants = self._resolve_participants(stored_records)

        summaries = [
            self._build_summary(
                meal, participants, stored_by_meal.get(meal.id, {}), absences, details_by_meal.get(meal.id), now
            )
            for meal in meals
        ]
        return _SummaryContext(
            summaries=summaries, participants=participants, absences=absences, details=details_by_meal
        )

    def get_overview(self, start_date: date, end_date: date) -> MealPlanAttendanceOverview:
        meals = self._get_meals(start_date, end_date)
        context = self._summaries_for(meals, start_date, end_date)

        return MealPlanAttendanceOverview(
            start_date=start_date,
            end_date=end_date,
            settings=self.settings,
            participants=context.participants,
            absences=context.absences,
            meals=context.summaries,
        )

    def get_summary(self, mealplan_id: int) -> MealPlanAttendanceSummary:
        meal = self._get_meal_or_raise(mealplan_id)
        return self._summaries_for([meal], meal.date, meal.date).summaries[0]

    def _get_meal_or_raise(self, mealplan_id: int) -> ReadPlanEntry:
        meal = self.repos.meals.get_one(mealplan_id)
        if not meal:
            raise MealPlanAttendanceError(f"mealplan entry {mealplan_id} not found")
        return meal

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def _get_or_create_details(self, mealplan_id: int) -> MealPlanEntryDetailsOut:
        existing = self.repos.mealplan_entry_details.get_by_mealplan(mealplan_id)
        if existing:
            return existing

        return self.repos.mealplan_entry_details.create(
            MealPlanEntryDetailsSave(group_id=self.group_id, household_id=self.household_id, mealplan_id=mealplan_id)
        )

    def set_attendance(
        self, mealplan_id: int, participant_id: UUID4, data: MealPlanAttendanceUpdate
    ) -> MealPlanAttendanceSummary:
        return self.set_attendance_bulk(
            mealplan_id,
            [
                MealPlanAttendanceBulkUpdate(
                    participant_id=participant_id,
                    status=data.status,
                    guest_count=data.guest_count,
                    note=data.note,
                )
            ],
        )

    def set_attendance_bulk(
        self, mealplan_id: int, updates: list[MealPlanAttendanceBulkUpdate]
    ) -> MealPlanAttendanceSummary:
        meal = self._get_meal_or_raise(mealplan_id)
        summary = self.get_summary(mealplan_id)

        if summary.is_locked:
            raise MealPlanLockedError(f"attendance for {meal.date} is closed")

        known_participants = {p.id: p for p in self.get_participants()}
        stored = {
            record.participant_id: record
            for record in self.repos.mealplan_attendance.get_by_mealplan_ids([mealplan_id])
        }
        now = datetime.now(UTC)

        for update in updates:
            if update.participant_id not in known_participants:
                raise MealPlanAttendanceError(f"participant {update.participant_id} is not part of this household")

            payload = MealPlanAttendanceSave(
                group_id=self.group_id,
                household_id=self.household_id,
                mealplan_id=mealplan_id,
                participant_id=update.participant_id,
                status=update.status,
                guest_count=update.guest_count,
                note=update.note,
                responded_at=now,
            )

            if existing := stored.get(update.participant_id):
                self.repos.mealplan_attendance.update(existing.id, payload)
            else:
                self.repos.mealplan_attendance.create(payload)

        return self.get_summary(mealplan_id)

    def update_details(self, mealplan_id: int, data: MealPlanEntryDetailsUpdate) -> MealPlanAttendanceSummary:
        self._get_meal_or_raise(mealplan_id)
        details = self._get_or_create_details(mealplan_id)

        save = MealPlanEntryDetailsSave(
            **data.model_dump(),
            group_id=self.group_id,
            household_id=self.household_id,
            mealplan_id=mealplan_id,
            reminder_sent_at=details.reminder_sent_at,
        )
        self.repos.mealplan_entry_details.update(details.id, save)

        return self.get_summary(mealplan_id)

    def lock_meal(self, mealplan_id: int) -> MealPlanAttendanceSummary:
        """
        Close a meal and freeze the projection.

        Every participant's effective answer -- their explicit one, or the default, or a
        forced decline because they are away -- is written to a real row, so the record
        stays stable even if defaults or absences change later.
        """

        summary = self.get_summary(mealplan_id)
        details = self._get_or_create_details(mealplan_id)

        stored = {
            record.participant_id: record
            for record in self.repos.mealplan_attendance.get_by_mealplan_ids([mealplan_id])
        }

        for attendee in summary.attendees:
            payload = MealPlanAttendanceSave(
                group_id=self.group_id,
                household_id=self.household_id,
                mealplan_id=mealplan_id,
                participant_id=attendee.participant_id,
                status=attendee.status,
                guest_count=attendee.guest_count,
                note=attendee.note,
                responded_at=stored[attendee.participant_id].responded_at
                if attendee.participant_id in stored
                else None,
            )

            if existing := stored.get(attendee.participant_id):
                self.repos.mealplan_attendance.update(existing.id, payload)
            else:
                self.repos.mealplan_attendance.create(payload)

        self.repos.mealplan_entry_details.update(
            details.id,
            MealPlanEntryDetailsSave(
                group_id=self.group_id,
                household_id=self.household_id,
                mealplan_id=mealplan_id,
                deadline_at=details.deadline_at,
                locked=True,
                servings_override=details.servings_override,
                cook_participant_id=details.cook_participant_id,
                shopper_participant_id=details.shopper_participant_id,
                reminder_sent_at=details.reminder_sent_at,
            ),
        )

        return self.get_summary(mealplan_id)

    def unlock_meal(self, mealplan_id: int, deadline_at: datetime | None = None) -> MealPlanAttendanceSummary:
        """
        Reopen a closed meal.

        A new deadline is always written, defaulting to 24 hours from now. Without one the
        household rule would put the cutoff back in the past and the meal would close again
        on the next request.
        """

        self._get_meal_or_raise(mealplan_id)
        details = self._get_or_create_details(mealplan_id)

        self.repos.mealplan_entry_details.update(
            details.id,
            MealPlanEntryDetailsSave(
                group_id=self.group_id,
                household_id=self.household_id,
                mealplan_id=mealplan_id,
                deadline_at=deadline_at or datetime.now(UTC) + DEFAULT_REOPEN_WINDOW,
                locked=False,
                servings_override=details.servings_override,
                cook_participant_id=details.cook_participant_id,
                shopper_participant_id=details.shopper_participant_id,
                reminder_sent_at=None,
            ),
        )

        return self.get_summary(mealplan_id)

    # ------------------------------------------------------------------
    # Scheduled work
    # ------------------------------------------------------------------

    def close_expired_meals(self, now: datetime | None = None) -> list[MealPlanAttendanceSummary]:
        """Lock every upcoming meal whose deadline has passed. Returns what was closed."""

        if not self.settings.enabled or not self.settings.auto_lock:
            return []

        now = now or datetime.now(UTC)
        today = now.date()
        end = today + timedelta(days=LOCK_LOOKAHEAD_DAYS)

        context = self._summaries_for(self._get_meals(today, end), today, end, now=now)

        # Anything already frozen has a details row saying so; only close the rest.
        def already_frozen(mealplan_id: int) -> bool:
            details = context.details.get(mealplan_id)
            return bool(details and details.locked)

        return [
            self.lock_meal(summary.mealplan_id)
            for summary in context.summaries
            if summary.is_locked and not already_frozen(summary.mealplan_id)
        ]

    def collect_due_reminders(self, now: datetime | None = None) -> list[MealPlanAttendanceSummary]:
        """
        Meals whose deadline is close enough to nag about, that nobody has been nagged for yet.

        Marks each meal as reminded before returning it, so a failure to deliver does not
        turn into a reminder loop.
        """

        if not self.settings.enabled or not self.settings.reminder_enabled:
            return []

        now = now or datetime.now(UTC)
        today = now.date()
        end = today + timedelta(days=LOCK_LOOKAHEAD_DAYS)
        window_end = now + timedelta(hours=self.settings.reminder_hours_before)

        context = self._summaries_for(self._get_meals(today, end), today, end, now=now)

        due: list[MealPlanAttendanceSummary] = []
        for summary in context.summaries:
            if summary.is_locked or not summary.deadline_at or summary.deadline_at > window_end:
                continue
            if not summary.pending_response_count:
                continue

            details = context.details.get(summary.mealplan_id)
            if details and details.reminder_sent_at:
                continue

            self._mark_reminder_sent(summary.mealplan_id, now)
            due.append(summary)

        return due

    def _mark_reminder_sent(self, mealplan_id: int, now: datetime) -> None:
        details = self._get_or_create_details(mealplan_id)
        self.repos.mealplan_entry_details.update(
            details.id,
            MealPlanEntryDetailsSave(
                group_id=self.group_id,
                household_id=self.household_id,
                mealplan_id=mealplan_id,
                deadline_at=details.deadline_at,
                locked=details.locked,
                servings_override=details.servings_override,
                cook_participant_id=details.cook_participant_id,
                shopper_participant_id=details.shopper_participant_id,
                reminder_sent_at=now,
            ),
        )

    def get_reminder_recipients(self, summary: MealPlanAttendanceSummary) -> list[tuple[str, str]]:
        """`(name, email)` pairs for the users who still owe an answer for this meal."""

        pending_user_ids = {
            attendee.user_id
            for attendee in summary.attendees
            if attendee.user_id and not attendee.has_responded and not attendee.is_absent
        }
        if not pending_user_ids:
            return []

        users = self.repos.users.multi_query({"household_id": self.household_id}, limit=None)
        return [
            (user.full_name or user.username or "", user.email)
            for user in users
            if user.id in pending_user_ids and user.email
        ]

    # ------------------------------------------------------------------
    # Shopping list
    # ------------------------------------------------------------------

    def add_planned_meals_to_shopping_list(
        self, request: MealPlanAttendanceShoppingListRequest
    ) -> MealPlanAttendanceShoppingListResult:
        """Push the planned meals of a date range onto a shopping list, scaled to the confirmations."""

        overview = self.get_overview(request.start_date, request.end_date)

        added: list[MealPlanAttendanceShoppingListEntry] = []
        skipped: list[str] = []
        recipe_params: list[ShoppingListAddRecipeParamsBulk] = []

        for summary in overview.meals:
            label = f"{summary.date} {summary.entry_type.value}"

            if not summary.recipe_id:
                skipped.append(f"{label}: no recipe attached")
                continue
            if request.only_locked and not summary.is_locked:
                skipped.append(f"{label}: attendance is still open")
                continue
            if summary.servings <= 0:
                skipped.append(f"{label}: nobody is eating along")
                continue

            recipe_params.append(
                ShoppingListAddRecipeParamsBulk(
                    recipe_id=summary.recipe_id, recipe_increment_quantity=summary.scale_factor
                )
            )
            added.append(
                MealPlanAttendanceShoppingListEntry(
                    mealplan_id=summary.mealplan_id,
                    recipe_id=summary.recipe_id,
                    recipe_name=summary.recipe_name,
                    servings=summary.servings,
                    scale_factor=summary.scale_factor,
                )
            )

        if recipe_params:
            ShoppingListService(self.repos).add_recipe_ingredients_to_list(request.shopping_list_id, recipe_params)

        return MealPlanAttendanceShoppingListResult(
            shopping_list_id=request.shopping_list_id, added=added, skipped=skipped
        )
