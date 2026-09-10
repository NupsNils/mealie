"""Schemas for the meal attendance module."""

from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from pydantic import UUID4, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.interfaces import LoaderOption

from mealie.db.models.household.mealplan_attendance import MealPlanRecipeSuggestion
from mealie.schema._mealie import MealieModel
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.schema.response.pagination import PaginationBase

from .new_meal import PlanEntryType


class AttendanceStatus(StrEnum):
    attending = "attending"
    declined = "declined"
    undecided = "undecided"


class AbsenceReason(StrEnum):
    vacation = "vacation"
    business_trip = "business_trip"
    away = "away"
    other = "other"


class DeadlineMode(StrEnum):
    weekly = "weekly"
    """A fixed weekday and time, shared by every meal in the window it closes."""

    relative = "relative"
    """A fixed number of days before each individual meal."""

    manual = "manual"
    """No automatic deadline; only per-meal overrides apply."""


class SuggestionStatus(StrEnum):
    open = "open"
    planned = "planned"
    rejected = "rejected"


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------


class MealPlanParticipantCreate(MealieModel):
    name: str = Field(..., min_length=1, max_length=255)
    user_id: UUID4 | None = None
    """Set for participants that are Mealie users. Guests leave this empty."""

    parent_id: UUID4 | None = None
    """For guests: the participant they belong to, e.g. somebody's partner."""

    default_attending: bool = True
    active: bool = True


class MealPlanParticipantUpdate(MealPlanParticipantCreate):
    id: UUID4


class MealPlanParticipantSave(MealPlanParticipantCreate):
    group_id: UUID4
    household_id: UUID4


class MealPlanParticipantOut(MealPlanParticipantSave):
    id: UUID4
    model_config = ConfigDict(from_attributes=True)

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


class MealPlanParticipantPagination(PaginationBase):
    items: list[MealPlanParticipantOut]


# ---------------------------------------------------------------------------
# Absences
# ---------------------------------------------------------------------------


class MealPlanAbsenceCreate(MealieModel):
    participant_id: UUID4
    start_date: date
    end_date: date
    reason: AbsenceReason = AbsenceReason.away
    note: str | None = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class MealPlanAbsenceUpdate(MealPlanAbsenceCreate):
    id: UUID4


class MealPlanAbsenceSave(MealPlanAbsenceCreate):
    group_id: UUID4
    household_id: UUID4


class MealPlanAbsenceOut(MealPlanAbsenceSave):
    id: UUID4
    model_config = ConfigDict(from_attributes=True)


class MealPlanAbsencePagination(PaginationBase):
    items: list[MealPlanAbsenceOut]


# ---------------------------------------------------------------------------
# Household settings
# ---------------------------------------------------------------------------


class MealPlanAttendanceSettingsUpdate(MealieModel):
    enabled: bool = False

    deadline_mode: DeadlineMode = DeadlineMode.weekly
    deadline_weekday: int = Field(3, ge=0, le=6)
    """Monday is 0, matching `datetime.date.weekday()`. Defaults to Thursday."""

    deadline_time: time = time(20, 0)
    deadline_lead_days: int = Field(1, ge=0, le=60)
    timezone: str = "UTC"

    auto_lock: bool = True
    reminder_enabled: bool = True
    reminder_hours_before: int = Field(24, ge=1, le=336)

    entry_types: list[PlanEntryType] = Field(default_factory=lambda: [PlanEntryType.dinner])
    """Which mealplan entry types take part in the attendance flow."""

    @field_validator("entry_types", mode="before")
    @classmethod
    def split_entry_types(cls, value: Any) -> Any:
        """The column stores a comma separated string; the API works with a list."""

        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"'{value}' is not a valid IANA timezone") from e

        return value


class MealPlanAttendanceSettingsSave(MealPlanAttendanceSettingsUpdate):
    group_id: UUID4
    household_id: UUID4

    def to_db_values(self) -> dict[str, Any]:
        """`entry_types` is a list on the wire but a comma separated string in the database."""

        values = self.model_dump()
        values["entry_types"] = ",".join(entry_type.value for entry_type in self.entry_types)
        return values


class MealPlanAttendanceSettingsOut(MealPlanAttendanceSettingsSave):
    id: UUID4
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Per-meal details (deadline, lock, roles)
# ---------------------------------------------------------------------------


class MealPlanEntryDetailsUpdate(MealieModel):
    deadline_at: datetime | None = None
    locked: bool = False
    servings_override: float | None = Field(None, ge=0)
    cook_participant_id: UUID4 | None = None
    shopper_participant_id: UUID4 | None = None


class MealPlanEntryDetailsSave(MealPlanEntryDetailsUpdate):
    group_id: UUID4
    household_id: UUID4
    mealplan_id: int
    reminder_sent_at: datetime | None = None


class MealPlanEntryDetailsOut(MealPlanEntryDetailsSave):
    id: UUID4
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Attendance records
# ---------------------------------------------------------------------------


class MealPlanAttendanceUpdate(MealieModel):
    status: AttendanceStatus
    guest_count: int = Field(0, ge=0, le=50)
    note: str | None = None


class MealPlanAttendanceSave(MealPlanAttendanceUpdate):
    group_id: UUID4
    household_id: UUID4
    mealplan_id: int
    participant_id: UUID4
    responded_at: datetime | None = None


class MealPlanAttendanceOut(MealPlanAttendanceSave):
    id: UUID4
    model_config = ConfigDict(from_attributes=True)


class MealPlanAttendanceBulkUpdate(MealieModel):
    """Update several participants for one meal in a single request."""

    participant_id: UUID4
    status: AttendanceStatus
    guest_count: int = Field(0, ge=0, le=50)
    note: str | None = None


# ---------------------------------------------------------------------------
# Computed views
# ---------------------------------------------------------------------------


class MealPlanAttendeeSummary(MealieModel):
    """One participant's row in a meal's attendance table."""

    participant_id: UUID4
    participant_name: str
    user_id: UUID4 | None = None
    parent_id: UUID4 | None = None
    is_guest: bool = False

    status: AttendanceStatus = AttendanceStatus.undecided
    guest_count: int = 0
    note: str | None = None

    has_responded: bool = False
    """False while the row still holds the participant's default answer."""

    is_absent: bool = False
    absence_reason: AbsenceReason | None = None


class MealPlanAttendanceSummary(MealieModel):
    """Everything the UI needs to render one planned meal."""

    mealplan_id: int
    date: date
    entry_type: PlanEntryType
    title: str = ""

    recipe_id: UUID4 | None = None
    recipe_name: str | None = None
    recipe_slug: str | None = None

    deadline_at: datetime | None = None
    is_locked: bool = False
    """Attendance can no longer be changed."""

    deadline_passed: bool = False
    """The cutoff is behind us. A meal can also be locked before that, by hand."""

    attendee_count: int = 0
    """Confirmations, including the extra guests each participant brings."""

    pending_response_count: int = 0
    servings: float = 0
    servings_override: float | None = None
    recipe_servings: float = 0
    """The recipe's own yield. Zero when the recipe does not declare one."""

    scale_factor: float = 1.0
    """`servings / recipe_servings`, i.e. what the recipe has to be multiplied by."""

    cook_participant_id: UUID4 | None = None
    shopper_participant_id: UUID4 | None = None

    attendees: list[MealPlanAttendeeSummary] = Field(default_factory=list)


class MealPlanAttendanceOverview(MealieModel):
    """A date range of meals plus the context needed to render them."""

    start_date: date
    end_date: date
    settings: MealPlanAttendanceSettingsOut
    participants: list[MealPlanParticipantOut] = Field(default_factory=list)
    absences: list[MealPlanAbsenceOut] = Field(default_factory=list)
    meals: list[MealPlanAttendanceSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Shopping list integration
# ---------------------------------------------------------------------------


class MealPlanAttendanceShoppingListRequest(MealieModel):
    shopping_list_id: UUID4
    start_date: date
    end_date: date
    only_locked: bool = True
    """Skip meals whose deadline has not passed yet, so portions cannot still change."""


class MealPlanAttendanceShoppingListEntry(MealieModel):
    mealplan_id: int
    recipe_id: UUID4
    recipe_name: str | None = None
    servings: float
    scale_factor: float


class MealPlanAttendanceShoppingListResult(MealieModel):
    shopping_list_id: UUID4
    added: list[MealPlanAttendanceShoppingListEntry] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    """Human readable reasons for meals that were left out."""


# ---------------------------------------------------------------------------
# Rolling plan: suggestions and rotation
# ---------------------------------------------------------------------------


class MealPlanSuggestionCreate(MealieModel):
    recipe_id: UUID4
    note: str | None = None


class MealPlanSuggestionUpdate(MealieModel):
    id: UUID4
    status: SuggestionStatus = SuggestionStatus.open
    note: str | None = None


class MealPlanSuggestionSave(MealPlanSuggestionCreate):
    group_id: UUID4
    household_id: UUID4
    created_by_id: UUID4 | None = None
    status: SuggestionStatus = SuggestionStatus.open


class MealPlanSuggestionOut(MealPlanSuggestionSave):
    id: UUID4
    recipe: RecipeSummary | None = None
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def loader_options(cls) -> list[LoaderOption]:
        return [joinedload(MealPlanRecipeSuggestion.recipe)]


class MealPlanSuggestionPagination(PaginationBase):
    items: list[MealPlanSuggestionOut]


class MealPlanRotationCandidate(MealieModel):
    """One scored proposal for an open slot in the rolling plan."""

    recipe: RecipeSummary
    score: float
    last_planned_on: date | None = None
    days_since_last: int | None = None
    favorite_count: int = 0
    is_suggested: bool = False
    suggested_by: list[str] = Field(default_factory=list)
    last_chosen_by: str | None = None
    reasons: list[str] = Field(default_factory=list)
    """Short explanations of why the recipe scored the way it did."""


class MealPlanRotationRequest(MealieModel):
    start_date: date
    end_date: date
    entry_type: PlanEntryType = PlanEntryType.dinner
    cooldown_weeks: int = Field(6, ge=0, le=52)
    """How long a recipe rests before it may come round again."""

    favorite_weight: float = Field(1.0, ge=0, le=10)
    suggestion_weight: float = Field(1.5, ge=0, le=10)
    fairness_weight: float = Field(1.0, ge=0, le=10)
    """Pushes down recipes last picked by whoever chose most recently."""

    limit: int = Field(5, ge=1, le=50)


class MealPlanRotationSlot(MealieModel):
    date: date
    entry_type: PlanEntryType
    candidates: list[MealPlanRotationCandidate] = Field(default_factory=list)


class MealPlanRotationProposal(MealieModel):
    cooldown_weeks: int
    slots: list[MealPlanRotationSlot] = Field(default_factory=list)
