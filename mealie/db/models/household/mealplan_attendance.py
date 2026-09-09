"""
Database models for the meal attendance module.

This module is intentionally self-contained: it never modifies existing recipe or
mealplan tables. Everything the module needs is stored in its own tables, with
`MealPlanEntryDetails` acting as a 1:1 side table for `group_meal_plans`. This keeps
the fork mergeable with upstream Mealie.
"""

import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
import sqlalchemy.orm as orm
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.datetime import NaiveDateTime
from .._model_utils.guid import GUID

if TYPE_CHECKING:
    from ..recipe import RecipeModel
    from ..users import User
    from .household import Household
    from .mealplan import GroupMealPlan


class MealPlanParticipant(SqlAlchemyBase, BaseMixins):
    """
    Somebody who can be counted towards a meal.

    A participant is either a Mealie user (`user_id` is set) or a guest such as a
    partner or child (`user_id` is null and `parent_id` points at the participant
    the guest belongs to). Modelling both in one table keeps `MealPlanAttendance`
    to a single foreign key instead of two mutually-exclusive nullable ones.
    """

    __tablename__ = "mealplan_participants"
    __table_args__ = (sa.UniqueConstraint("household_id", "user_id", name="mealplan_participant_household_user_key"),)

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("households.id"), nullable=False, index=True
    )
    household: Mapped["Household"] = orm.relationship("Household", back_populates="mealplan_participants")

    user_id: FilterableColumn[GUID | None] = mapped_column(GUID, sa.ForeignKey("users.id"), nullable=True, index=True)
    user: Mapped[Optional["User"]] = orm.relationship("User", back_populates="mealplan_participants")

    parent_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, sa.ForeignKey("mealplan_participants.id"), nullable=True, index=True
    )
    parent: Mapped[Optional["MealPlanParticipant"]] = orm.relationship(
        "MealPlanParticipant", back_populates="guests", remote_side=[id]
    )
    guests: Mapped[list["MealPlanParticipant"]] = orm.relationship(
        "MealPlanParticipant", back_populates="parent", cascade="all, delete-orphan"
    )

    name: FilterableColumn[str] = mapped_column(sa.String, nullable=False, index=True)
    """Display name. Mirrors the user's name for linked participants, free text for guests."""

    default_attending: FilterableColumn[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    """The status new attendance rows start out with. Users default to yes, guests to no."""

    active: FilterableColumn[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    """Inactive participants keep their history but are no longer added to new meals."""

    attendance: Mapped[list["MealPlanAttendance"]] = orm.relationship(
        "MealPlanAttendance", back_populates="participant", cascade="all, delete-orphan"
    )
    absences: Mapped[list["MealPlanAbsence"]] = orm.relationship(
        "MealPlanAbsence", back_populates="participant", cascade="all, delete-orphan"
    )

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class MealPlanAttendance(SqlAlchemyBase, BaseMixins):
    """One participant's answer for one planned meal."""

    __tablename__ = "mealplan_attendance"
    __table_args__ = (
        sa.UniqueConstraint("mealplan_id", "participant_id", name="mealplan_attendance_mealplan_participant_key"),
    )

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("households.id"), nullable=False, index=True
    )

    mealplan_id: FilterableColumn[int] = mapped_column(
        sa.Integer, sa.ForeignKey("group_meal_plans.id"), nullable=False, index=True
    )
    mealplan: Mapped["GroupMealPlan"] = orm.relationship("GroupMealPlan", back_populates="attendance")

    participant_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("mealplan_participants.id"), nullable=False, index=True
    )
    participant: Mapped["MealPlanParticipant"] = orm.relationship("MealPlanParticipant", back_populates="attendance")

    status: FilterableColumn[str] = mapped_column(sa.String, nullable=False, default="undecided", index=True)
    """One of `attending`, `declined`, `undecided`."""

    guest_count: FilterableColumn[int] = mapped_column(sa.Integer, nullable=False, default=0)
    """Additional unnamed guests this participant brings along."""

    note: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    responded_at: FilterableColumn[datetime.datetime | None] = mapped_column(NaiveDateTime, nullable=True)
    """Null means the status is still the default and the participant has not answered yet."""

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class MealPlanEntryDetails(SqlAlchemyBase, BaseMixins):
    """
    Attendance metadata for a single mealplan entry.

    Kept in a side table so `group_meal_plans` stays untouched.
    """

    __tablename__ = "mealplan_entry_details"
    __table_args__ = (sa.UniqueConstraint("mealplan_id", name="mealplan_entry_details_mealplan_key"),)

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("households.id"), nullable=False, index=True
    )

    mealplan_id: FilterableColumn[int] = mapped_column(
        sa.Integer, sa.ForeignKey("group_meal_plans.id"), nullable=False, index=True
    )
    mealplan: Mapped["GroupMealPlan"] = orm.relationship("GroupMealPlan", back_populates="details")

    deadline_at: FilterableColumn[datetime.datetime | None] = mapped_column(NaiveDateTime, nullable=True, index=True)
    """Explicit deadline. When null the household settings derive one from the meal date."""

    locked: FilterableColumn[bool] = mapped_column(sa.Boolean, nullable=False, default=False, index=True)
    servings_override: FilterableColumn[float | None] = mapped_column(sa.Float, nullable=True)
    """Manual portion count, used instead of the number of confirmations."""

    cook_participant_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, sa.ForeignKey("mealplan_participants.id"), nullable=True, index=True
    )
    shopper_participant_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, sa.ForeignKey("mealplan_participants.id"), nullable=True, index=True
    )

    reminder_sent_at: FilterableColumn[datetime.datetime | None] = mapped_column(NaiveDateTime, nullable=True)

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class MealPlanAttendanceSettings(SqlAlchemyBase, BaseMixins):
    """Per-household configuration for the attendance module."""

    __tablename__ = "mealplan_attendance_settings"
    __table_args__ = (sa.UniqueConstraint("household_id", name="mealplan_attendance_settings_household_key"),)

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("households.id"), nullable=False, index=True
    )
    household: Mapped["Household"] = orm.relationship("Household", back_populates="mealplan_attendance_settings")

    enabled: FilterableColumn[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    deadline_mode: FilterableColumn[str] = mapped_column(sa.String, nullable=False, default="weekly")
    """One of `weekly`, `relative`, `manual`."""

    deadline_weekday: FilterableColumn[int] = mapped_column(sa.Integer, nullable=False, default=3)
    """`weekly` mode: cutoff weekday, Monday is 0 (matches `datetime.date.weekday()`)."""

    deadline_time: Mapped[datetime.time] = mapped_column(sa.Time, nullable=False, default=datetime.time(20, 0))
    """Local wall-clock time of the cutoff."""

    deadline_lead_days: FilterableColumn[int] = mapped_column(sa.Integer, nullable=False, default=1)
    """`relative` mode: how many days before the meal the cutoff falls."""

    timezone: Mapped[str] = mapped_column(sa.String, nullable=False, default="UTC")
    """IANA name used to turn `deadline_time` into an absolute instant."""

    auto_lock: FilterableColumn[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    reminder_enabled: FilterableColumn[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    reminder_hours_before: FilterableColumn[int] = mapped_column(sa.Integer, nullable=False, default=24)

    entry_types: Mapped[str] = mapped_column(sa.String, nullable=False, default="dinner")
    """Comma separated mealplan entry types that require attendance, e.g. `lunch,dinner`."""

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class MealPlanAbsence(SqlAlchemyBase, BaseMixins):
    """A period a participant is away and cannot join meals."""

    __tablename__ = "mealplan_absences"

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("households.id"), nullable=False, index=True
    )

    participant_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("mealplan_participants.id"), nullable=False, index=True
    )
    participant: Mapped["MealPlanParticipant"] = orm.relationship("MealPlanParticipant", back_populates="absences")

    start_date: FilterableColumn[datetime.date] = mapped_column(sa.Date, nullable=False, index=True)
    end_date: FilterableColumn[datetime.date] = mapped_column(sa.Date, nullable=False, index=True)

    reason: FilterableColumn[str] = mapped_column(sa.String, nullable=False, default="away")
    """One of `vacation`, `business_trip`, `away`, `other`."""

    note: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class MealPlanRecipeSuggestion(SqlAlchemyBase, BaseMixins):
    """A recipe somebody proposed for one of the next meals."""

    __tablename__ = "mealplan_recipe_suggestions"
    __table_args__ = (
        sa.UniqueConstraint("household_id", "recipe_id", "created_by_id", name="mealplan_suggestion_recipe_user_key"),
    )

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(
        GUID, sa.ForeignKey("households.id"), nullable=False, index=True
    )

    recipe_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("recipes.id"), nullable=False, index=True)
    recipe: Mapped["RecipeModel"] = orm.relationship("RecipeModel", back_populates="mealplan_suggestions")

    created_by_id: FilterableColumn[GUID | None] = mapped_column(
        GUID, sa.ForeignKey("users.id"), nullable=True, index=True
    )
    user: Mapped[Optional["User"]] = orm.relationship("User", back_populates="mealplan_suggestions")

    status: FilterableColumn[str] = mapped_column(sa.String, nullable=False, default="open", index=True)
    """One of `open`, `planned`, `rejected`."""

    note: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    @auto_init()
    def __init__(self, **_) -> None:
        pass
