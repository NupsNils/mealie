from collections.abc import Iterable
from datetime import date, datetime

from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.orm import Session

from mealie.db.models.household.mealplan_attendance import (
    MealPlanAbsence,
    MealPlanAttendance,
    MealPlanAttendanceSettings,
    MealPlanEntryDetails,
    MealPlanParticipant,
)
from mealie.schema.meal_plan.attendance import (
    MealPlanAbsenceOut,
    MealPlanAttendanceOut,
    MealPlanEntryDetailsOut,
    MealPlanParticipantOut,
)

from .repository_generic import HouseholdRepositoryGeneric


class RepositoryMealPlanParticipants(HouseholdRepositoryGeneric[MealPlanParticipantOut, MealPlanParticipant]):
    def get_active(self) -> list[MealPlanParticipantOut]:
        """Participants that should be added to newly planned meals, ordered for stable rendering."""

        stmt = (
            self._query()
            .filter_by(**self._filter_builder(active=True))
            .order_by(MealPlanParticipant.parent_id.is_(None).desc(), MealPlanParticipant.name)
        )
        results = self.session.execute(stmt).unique().scalars().all()
        return [self.schema.model_validate(x) for x in results]

    def get_by_user(self, user_id: UUID4) -> MealPlanParticipantOut | None:
        stmt = self._query().filter_by(**self._filter_builder(user_id=user_id))
        result = self.session.execute(stmt).unique().scalars().first()
        return self.schema.model_validate(result) if result else None


class RepositoryMealPlanAttendance(HouseholdRepositoryGeneric[MealPlanAttendanceOut, MealPlanAttendance]):
    def get_by_mealplan_ids(self, mealplan_ids: Iterable[int]) -> list[MealPlanAttendanceOut]:
        mealplan_ids = list(mealplan_ids)
        if not mealplan_ids:
            return []

        stmt = (
            self._query().filter_by(**self._filter_builder()).filter(MealPlanAttendance.mealplan_id.in_(mealplan_ids))
        )
        results = self.session.execute(stmt).unique().scalars().all()
        return [self.schema.model_validate(x) for x in results]


class RepositoryMealPlanEntryDetails(HouseholdRepositoryGeneric[MealPlanEntryDetailsOut, MealPlanEntryDetails]):
    def get_by_mealplan(self, mealplan_id: int) -> MealPlanEntryDetailsOut | None:
        stmt = self._query().filter_by(**self._filter_builder(mealplan_id=mealplan_id))
        result = self.session.execute(stmt).unique().scalars().first()
        return self.schema.model_validate(result) if result else None

    def get_by_mealplan_ids(self, mealplan_ids: Iterable[int]) -> list[MealPlanEntryDetailsOut]:
        mealplan_ids = list(mealplan_ids)
        if not mealplan_ids:
            return []

        stmt = (
            self._query().filter_by(**self._filter_builder()).filter(MealPlanEntryDetails.mealplan_id.in_(mealplan_ids))
        )
        results = self.session.execute(stmt).unique().scalars().all()
        return [self.schema.model_validate(x) for x in results]

    def get_pending_reminders(self, deadline_before: datetime) -> list[MealPlanEntryDetailsOut]:
        """Unlocked meals with an explicit deadline that is due and whose reminder has not gone out."""

        stmt = (
            self._query()
            .filter_by(**self._filter_builder())
            .filter(
                MealPlanEntryDetails.locked.is_(False),
                MealPlanEntryDetails.reminder_sent_at.is_(None),
                MealPlanEntryDetails.deadline_at.is_not(None),
                MealPlanEntryDetails.deadline_at <= deadline_before,
            )
        )
        results = self.session.execute(stmt).unique().scalars().all()
        return [self.schema.model_validate(x) for x in results]


class RepositoryMealPlanAbsences(HouseholdRepositoryGeneric[MealPlanAbsenceOut, MealPlanAbsence]):
    def get_overlapping(self, start_date: date, end_date: date) -> list[MealPlanAbsenceOut]:
        """Absences that touch the given range at any point."""

        stmt = (
            self._query()
            .filter_by(**self._filter_builder())
            .filter(MealPlanAbsence.start_date <= end_date, MealPlanAbsence.end_date >= start_date)
            .order_by(MealPlanAbsence.start_date)
        )
        results = self.session.execute(stmt).unique().scalars().all()
        return [self.schema.model_validate(x) for x in results]


def household_ids_with_attendance_enabled(session: Session) -> list[tuple[UUID4, UUID4]]:
    """
    Every (group_id, household_id) pair that has switched the module on.

    Used by the scheduler, which runs without a request context and therefore has no
    household-scoped repository to work with.
    """

    stmt = select(MealPlanAttendanceSettings.group_id, MealPlanAttendanceSettings.household_id).filter(
        MealPlanAttendanceSettings.enabled.is_(True)
    )
    return [(row[0], row[1]) for row in session.execute(stmt).all()]
