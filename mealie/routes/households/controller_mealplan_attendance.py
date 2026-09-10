from datetime import UTC, date, datetime, timedelta
from functools import cached_property
from typing import NoReturn

from fastapi import Depends, HTTPException, status
from pydantic import UUID4

from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.mixins import HttpRepo
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema import mapper
from mealie.schema.meal_plan.attendance import (
    MealPlanAbsenceCreate,
    MealPlanAbsenceOut,
    MealPlanAbsencePagination,
    MealPlanAbsenceSave,
    MealPlanAbsenceUpdate,
    MealPlanAttendanceBulkUpdate,
    MealPlanAttendanceOverview,
    MealPlanAttendanceSettingsOut,
    MealPlanAttendanceSettingsUpdate,
    MealPlanAttendanceShoppingListRequest,
    MealPlanAttendanceShoppingListResult,
    MealPlanAttendanceSummary,
    MealPlanAttendanceUpdate,
    MealPlanEntryDetailsUpdate,
    MealPlanParticipantCreate,
    MealPlanParticipantOut,
    MealPlanParticipantPagination,
    MealPlanParticipantSave,
    MealPlanParticipantUpdate,
    MealPlanRotationProposal,
    MealPlanRotationRequest,
    MealPlanSuggestionCreate,
    MealPlanSuggestionOut,
    MealPlanSuggestionPagination,
    MealPlanSuggestionSave,
    MealPlanSuggestionUpdate,
)
from mealie.schema.response.pagination import PaginationQuery
from mealie.schema.response.responses import ErrorResponse
from mealie.services.household_services.mealplan_attendance import (
    MealPlanAttendanceError,
    MealPlanAttendanceService,
    MealPlanLockedError,
)
from mealie.services.household_services.mealplan_rotation import MealPlanRotationService

TAGS = ["Households: Meal Attendance"]

router = UserAPIRouter(prefix="/households/mealplan-attendance", tags=TAGS)
participants_router = UserAPIRouter(prefix="/households/mealplan-participants", tags=TAGS)
absences_router = UserAPIRouter(prefix="/households/mealplan-absences", tags=TAGS)
suggestions_router = UserAPIRouter(prefix="/households/mealplan-suggestions", tags=TAGS)
meal_router = UserAPIRouter(prefix="/households/mealplans", tags=TAGS)

DEFAULT_RANGE_DAYS = 14


class _AttendanceControllerBase(BaseUserController):
    @cached_property
    def service(self) -> MealPlanAttendanceService:
        return MealPlanAttendanceService(self.repos)

    def handle(self, ex: Exception) -> NoReturn:
        """Turn the service's domain errors into the right HTTP status."""

        if isinstance(ex, MealPlanLockedError):
            raise HTTPException(status.HTTP_423_LOCKED, detail=ErrorResponse.respond(message=str(ex))) from ex
        if isinstance(ex, MealPlanAttendanceError):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message=str(ex))) from ex
        raise ex


@controller(router)
class MealPlanAttendanceController(_AttendanceControllerBase):
    @router.get("/settings", response_model=MealPlanAttendanceSettingsOut)
    def get_settings(self):
        return self.service.settings

    @router.put("/settings", response_model=MealPlanAttendanceSettingsOut)
    def update_settings(self, data: MealPlanAttendanceSettingsUpdate):
        self.checks.can_manage_household()
        return self.service.update_settings(data)

    @router.get("", response_model=MealPlanAttendanceOverview)
    def get_overview(self, start_date: date | None = None, end_date: date | None = None):
        """
        Every meal in the range together with who is eating along.

        Defaults to the next two weeks when no range is given.
        """

        start = start_date or datetime.now(UTC).date()
        end = end_date or start + timedelta(days=DEFAULT_RANGE_DAYS)
        if end < start:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse.respond(message="end_date must not be before start_date"),
            )

        return self.service.get_overview(start, end)

    @router.post("/shopping-list", response_model=MealPlanAttendanceShoppingListResult)
    def add_to_shopping_list(self, data: MealPlanAttendanceShoppingListRequest):
        """Add the planned meals of a range to a shopping list, scaled to the confirmations."""

        if data.end_date < data.start_date:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse.respond(message="end_date must not be before start_date"),
            )

        try:
            return self.service.add_planned_meals_to_shopping_list(data)
        except Exception as ex:
            self.handle(ex)


@controller(meal_router)
class MealPlanEntryAttendanceController(_AttendanceControllerBase):
    @meal_router.get("/{item_id}/attendance", response_model=MealPlanAttendanceSummary)
    def get_attendance(self, item_id: int):
        try:
            return self.service.get_summary(item_id)
        except Exception as ex:
            self.handle(ex)

    @meal_router.put("/{item_id}/attendance/{participant_id}", response_model=MealPlanAttendanceSummary)
    def set_attendance(self, item_id: int, participant_id: UUID4, data: MealPlanAttendanceUpdate):
        try:
            return self.service.set_attendance(item_id, participant_id, data)
        except Exception as ex:
            self.handle(ex)

    @meal_router.put("/{item_id}/attendance", response_model=MealPlanAttendanceSummary)
    def set_attendance_bulk(self, item_id: int, data: list[MealPlanAttendanceBulkUpdate]):
        """Answer for several participants at once, e.g. for yourself and your partner."""

        try:
            return self.service.set_attendance_bulk(item_id, data)
        except Exception as ex:
            self.handle(ex)

    @meal_router.put("/{item_id}/attendance-details", response_model=MealPlanAttendanceSummary)
    def update_details(self, item_id: int, data: MealPlanEntryDetailsUpdate):
        """Set the deadline override, the portion override and who cooks or shops."""

        self.checks.can_manage_household()
        try:
            return self.service.update_details(item_id, data)
        except Exception as ex:
            self.handle(ex)

    @meal_router.post("/{item_id}/attendance/lock", response_model=MealPlanAttendanceSummary)
    def lock(self, item_id: int):
        self.checks.can_manage_household()
        try:
            return self.service.lock_meal(item_id)
        except Exception as ex:
            self.handle(ex)

    @meal_router.post("/{item_id}/attendance/unlock", response_model=MealPlanAttendanceSummary)
    def unlock(self, item_id: int, deadline_at: datetime | None = None):
        """
        Reopen a closed meal.

        Without `deadline_at` the meal stays open for another 24 hours; the household rule
        would otherwise put the cutoff back in the past and close it again immediately.
        """

        self.checks.can_manage_household()
        try:
            return self.service.unlock_meal(item_id, deadline_at)
        except Exception as ex:
            self.handle(ex)


@controller(participants_router)
class MealPlanParticipantController(_AttendanceControllerBase):
    @cached_property
    def repo(self):
        return self.repos.mealplan_participants

    @cached_property
    def mixins(self):
        return HttpRepo[MealPlanParticipantCreate, MealPlanParticipantOut, MealPlanParticipantUpdate](
            self.repo, self.logger
        )

    @participants_router.get("", response_model=MealPlanParticipantPagination)
    def get_all(self, q: PaginationQuery = Depends(PaginationQuery)):
        response = self.repo.page_all(pagination=q, override=MealPlanParticipantOut)
        response.set_pagination_guides(participants_router.url_path_for("get_all"), q.model_dump())
        return response

    @participants_router.post("/sync", response_model=list[MealPlanParticipantOut])
    def sync_from_users(self):
        """Create a participant for every household member that does not have one yet."""

        self.checks.can_manage_household()
        return self.service.sync_participants_from_users()

    @participants_router.post("", response_model=MealPlanParticipantOut, status_code=201)
    def create_one(self, data: MealPlanParticipantCreate):
        self.checks.can_manage_household()
        save = mapper.cast(data, MealPlanParticipantSave, group_id=self.group_id, household_id=self.household_id)
        return self.mixins.create_one(save)

    @participants_router.get("/{item_id}", response_model=MealPlanParticipantOut)
    def get_one(self, item_id: UUID4):
        return self.mixins.get_one(item_id)

    @participants_router.put("/{item_id}", response_model=MealPlanParticipantOut)
    def update_one(self, item_id: UUID4, data: MealPlanParticipantUpdate):
        self.checks.can_manage_household()
        save = mapper.cast(data, MealPlanParticipantSave, group_id=self.group_id, household_id=self.household_id)
        return self.mixins.update_one(save, item_id)

    @participants_router.delete("/{item_id}", response_model=MealPlanParticipantOut)
    def delete_one(self, item_id: UUID4):
        self.checks.can_manage_household()
        return self.mixins.delete_one(item_id)


@controller(absences_router)
class MealPlanAbsenceController(_AttendanceControllerBase):
    @cached_property
    def repo(self):
        return self.repos.mealplan_absences

    @cached_property
    def mixins(self):
        return HttpRepo[MealPlanAbsenceCreate, MealPlanAbsenceOut, MealPlanAbsenceUpdate](self.repo, self.logger)

    @absences_router.get("", response_model=MealPlanAbsencePagination)
    def get_all(self, q: PaginationQuery = Depends(PaginationQuery)):
        response = self.repo.page_all(pagination=q, override=MealPlanAbsenceOut)
        response.set_pagination_guides(absences_router.url_path_for("get_all"), q.model_dump())
        return response

    @absences_router.post("", response_model=MealPlanAbsenceOut, status_code=201)
    def create_one(self, data: MealPlanAbsenceCreate):
        self._assert_own_participant(data.participant_id)
        save = mapper.cast(data, MealPlanAbsenceSave, group_id=self.group_id, household_id=self.household_id)
        return self.mixins.create_one(save)

    @absences_router.get("/{item_id}", response_model=MealPlanAbsenceOut)
    def get_one(self, item_id: UUID4):
        return self.mixins.get_one(item_id)

    @absences_router.put("/{item_id}", response_model=MealPlanAbsenceOut)
    def update_one(self, item_id: UUID4, data: MealPlanAbsenceUpdate):
        self._assert_own_participant(data.participant_id)
        save = mapper.cast(data, MealPlanAbsenceSave, group_id=self.group_id, household_id=self.household_id)
        return self.mixins.update_one(save, item_id)

    @absences_router.delete("/{item_id}", response_model=MealPlanAbsenceOut)
    def delete_one(self, item_id: UUID4):
        existing = self.mixins.get_one(item_id)
        self._assert_own_participant(existing.participant_id)
        return self.mixins.delete_one(item_id)

    def _assert_own_participant(self, participant_id: UUID4) -> None:
        """
        Anyone may record absences for themselves and their own guests; household
        managers may do it for everybody.
        """

        if self.user.can_manage_household:
            return

        participant = self.repos.mealplan_participants.get_one(participant_id)
        if not participant:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message="participant not found")
            )

        owner_id = participant.user_id
        if owner_id is None and participant.parent_id:
            parent = self.repos.mealplan_participants.get_one(participant.parent_id)
            owner_id = parent.user_id if parent else None

        if owner_id != self.user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse.respond(message="you can only manage your own absences"),
            )


@controller(suggestions_router)
class MealPlanSuggestionController(BaseUserController):
    @cached_property
    def service(self) -> MealPlanRotationService:
        return MealPlanRotationService(self.repos)

    @cached_property
    def mixins(self):
        return HttpRepo[MealPlanSuggestionCreate, MealPlanSuggestionOut, MealPlanSuggestionUpdate](
            self.repos.mealplan_suggestions, self.logger, self.registered_exceptions
        )

    @suggestions_router.get("", response_model=MealPlanSuggestionPagination)
    def get_all(self, q: PaginationQuery = Depends(PaginationQuery)):
        response = self.repos.mealplan_suggestions.page_all(pagination=q, override=MealPlanSuggestionOut)
        response.set_pagination_guides(suggestions_router.url_path_for("get_all"), q.model_dump())
        return response

    @suggestions_router.post("", response_model=MealPlanSuggestionOut, status_code=201)
    def create_one(self, data: MealPlanSuggestionCreate):
        """
        Anyone in the household may propose a recipe.

        Routed through the mixin so proposing the same recipe twice comes back as a
        conflict rather than an unhandled integrity error.
        """

        save = mapper.cast(
            data,
            MealPlanSuggestionSave,
            group_id=self.group_id,
            household_id=self.household_id,
            created_by_id=self.user.id,
        )
        return self.mixins.create_one(save)

    @suggestions_router.post("/rotation", response_model=MealPlanRotationProposal)
    def get_rotation(self, data: MealPlanRotationRequest):
        """
        Ranked proposals for the open slots in a date range.

        Favourites rank higher, recipes still inside their cooldown are left out, and
        dishes last chosen by whoever has been deciding most are pushed down.
        """

        if data.end_date < data.start_date:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse.respond(message="end_date must not be before start_date"),
            )

        return self.service.build_proposal(data)

    @suggestions_router.put("/{item_id}", response_model=MealPlanSuggestionOut)
    def update_one(self, item_id: UUID4, data: MealPlanSuggestionUpdate):
        self._assert_may_edit(item_id)
        return self.service.update_suggestion(data.model_copy(update={"id": item_id}))

    @suggestions_router.delete("/{item_id}", response_model=MealPlanSuggestionOut)
    def delete_one(self, item_id: UUID4):
        self._assert_may_edit(item_id)
        return self.repos.mealplan_suggestions.delete(item_id)

    def _assert_may_edit(self, item_id: UUID4) -> None:
        suggestion = self.repos.mealplan_suggestions.get_one(item_id)
        if not suggestion:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message="suggestion not found"))

        if suggestion.created_by_id != self.user.id and not self.user.can_manage_household:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse.respond(message="you can only change your own suggestions"),
            )
