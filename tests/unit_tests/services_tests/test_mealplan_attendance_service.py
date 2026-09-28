from datetime import UTC, date, datetime, time

import pytest

from mealie.lang.providers import get_locale_provider
from mealie.schema.meal_plan.attendance import DeadlineMode, MealPlanAttendanceSettingsUpdate
from mealie.schema.meal_plan.new_meal import PlanEntryType
from mealie.services.household_services.mealplan_attendance import (
    compute_deadline_for,
    compute_scale_factor,
)

THURSDAY = 3


def settings(**overrides) -> MealPlanAttendanceSettingsUpdate:
    base = {
        "deadline_mode": DeadlineMode.weekly,
        "deadline_weekday": THURSDAY,
        "deadline_time": time(20, 0),
        "timezone": "Europe/Berlin",
        "entry_types": [PlanEntryType.dinner],
    }
    return MealPlanAttendanceSettingsUpdate(**{**base, **overrides})


class WeeklyDeadlineTests:
    """
    The reference case: a Thursday 20:00 cutoff closes the whole following week at once,
    so Sunday, Monday and Tuesday all share one deadline.
    """

    @pytest.mark.parametrize(
        ("meal_day", "expected_cutoff_day"),
        [
            (date(2026, 9, 13), date(2026, 9, 10)),  # Sunday  -> preceding Thursday
            (date(2026, 9, 14), date(2026, 9, 10)),  # Monday  -> same Thursday
            (date(2026, 9, 15), date(2026, 9, 10)),  # Tuesday -> same Thursday
            (date(2026, 9, 11), date(2026, 9, 10)),  # Friday  -> Thursday just gone
        ],
    )
    def test_meals_in_one_window_share_a_deadline(self, meal_day: date, expected_cutoff_day: date):
        deadline = compute_deadline_for(settings(), meal_day)

        assert deadline is not None
        # 20:00 Berlin time is 18:00 UTC while summer time is in effect.
        assert deadline == datetime(
            expected_cutoff_day.year, expected_cutoff_day.month, expected_cutoff_day.day, 18, 0, tzinfo=UTC
        )

    def test_a_meal_on_the_cutoff_weekday_uses_the_previous_week(self):
        """Otherwise a Thursday meal would close at 20:00 on the very same day."""

        deadline = compute_deadline_for(settings(), date(2026, 9, 17))  # a Thursday

        assert deadline is not None
        assert deadline.date() == date(2026, 9, 10)

    def test_winter_time_shifts_the_utc_instant(self):
        deadline = compute_deadline_for(settings(), date(2026, 12, 6))

        assert deadline is not None
        # 20:00 Berlin is 19:00 UTC outside of summer time.
        assert deadline == datetime(2026, 12, 3, 19, 0, tzinfo=UTC)


class OtherDeadlineModeTests:
    def test_relative_counts_back_from_the_meal(self):
        deadline = compute_deadline_for(
            settings(deadline_mode=DeadlineMode.relative, deadline_lead_days=2), date(2026, 9, 13)
        )

        assert deadline is not None
        assert deadline.date() == date(2026, 9, 11)

    def test_manual_has_no_automatic_deadline(self):
        assert compute_deadline_for(settings(deadline_mode=DeadlineMode.manual), date(2026, 9, 13)) is None


class ScaleFactorTests:
    def test_scales_a_recipe_up_to_the_confirmations(self):
        """The example from the brief: a recipe for four, seven people eating along."""

        assert compute_scale_factor(servings=7, recipe_servings=4) == pytest.approx(1.75)

    def test_scales_down_as_well(self):
        assert compute_scale_factor(servings=2, recipe_servings=4) == pytest.approx(0.5)

    @pytest.mark.parametrize(("servings", "recipe_servings"), [(0, 4), (7, 0), (0, 0)])
    def test_falls_back_to_one_when_there_is_nothing_to_scale(self, servings: float, recipe_servings: float):
        assert compute_scale_factor(servings, recipe_servings) == 1.0


class SchedulerMessageTests:
    """The scheduler's notifications pick a plural form, so `count` must be applied before the meal."""

    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (1, "Für Lasagne am 04.10.2026 fehlt noch 1 Antwort"),
            (3, "Für Lasagne am 04.10.2026 fehlen noch 3 Antworten"),
        ],
    )
    def test_reminder_notification_in_german(self, count: int, expected: str):
        t = get_locale_provider("de-DE").t
        meal = t("mealplan.attendance.meal-on-date", meal="Lasagne", date="04.10.2026")

        assert t("mealplan.attendance.reminder-notification", count=count, meal=meal) == expected

    def test_closed_notification_in_english(self):
        t = get_locale_provider("en-US").t

        message = t("mealplan.attendance.closed-notification", count=7, meal="Lasagne on 10/04/2026")

        assert message == "Attendance for Lasagne on 10/04/2026 closed with 7 confirmations"

    def test_german_reminder_email_body(self):
        body = get_locale_provider("de-DE").t(
            "emails.mealplan-attendance.reminder_body", meal="Lasagne am 04.10.2026", deadline="02.10.2026, 20:00 Uhr"
        )

        assert body == "Isst du mit? Lasagne am 04.10.2026. Bitte antworte bis 02.10.2026, 20:00 Uhr."
