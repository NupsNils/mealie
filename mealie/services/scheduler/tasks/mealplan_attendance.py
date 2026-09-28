"""
Hourly upkeep for the meal attendance module.

Three jobs, in this order: once a week fill the empty days from the rolling plan, nag the
people who still owe an answer, then close the meals whose deadline has passed. Closing
before reminding would lock a meal in the same run that was supposed to remind people about it.
"""

from datetime import timedelta

from pydantic import UUID4
from sqlalchemy.orm import Session

from mealie.core.root_logger import get_logger
from mealie.db.db_setup import session_context
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.repos.repository_mealplan_attendance import household_ids_with_attendance_enabled
from mealie.schema.meal_plan.attendance import MealPlanAttendanceSummary, MealPlanRotationRequest
from mealie.schema.user.user import DEFAULT_INTEGRATION_ID
from mealie.services.email.email_service import EmailService
from mealie.services.event_bus_service.event_bus_service import EventBusService
from mealie.services.event_bus_service.event_types import (
    EventMealplanAttendanceData,
    EventOperation,
    EventTypes,
)
from mealie.services.household_services.mealplan_attendance import MealPlanAttendanceService
from mealie.services.household_services.mealplan_rotation import MealPlanRotationService

logger = get_logger()


def _event_data(summary: MealPlanAttendanceSummary, operation: EventOperation) -> EventMealplanAttendanceData:
    return EventMealplanAttendanceData(
        operation=operation,
        mealplan_id=summary.mealplan_id,
        date=summary.date,
        recipe_name=summary.recipe_name,
        deadline_at=summary.deadline_at,
        attendee_count=summary.attendee_count,
        pending_response_count=summary.pending_response_count,
    )


def _process_household(session: Session, group_id: UUID4, household_id: UUID4) -> None:
    repos = get_repositories(session, group_id=group_id, household_id=household_id)
    service = MealPlanAttendanceService(repos)
    event_bus = EventBusService(session=session)

    try:
        auto_plan(repos, service)
    except Exception:
        # A failed plan must not keep the reminders and deadlines below from running.
        session.rollback()
        logger.exception("rolling plan failed for household %s", household_id)

    for summary in service.collect_due_reminders():
        meal = service.describe_meal(summary)
        _send_reminder_emails(service, summary, meal)

        event_bus.dispatch(
            integration_id=DEFAULT_INTEGRATION_ID,
            group_id=group_id,
            household_id=household_id,
            event_type=EventTypes.mealplan_attendance_reminder,
            document_data=_event_data(summary, EventOperation.info),
            # `count` goes first: it picks the plural form before the meal's name is filled in.
            message=service.translator.t(
                "mealplan.attendance.reminder-notification", count=summary.pending_response_count, meal=meal
            ),
        )

    for summary in service.close_expired_meals():
        event_bus.dispatch(
            integration_id=DEFAULT_INTEGRATION_ID,
            group_id=group_id,
            household_id=household_id,
            event_type=EventTypes.mealplan_attendance_closed,
            document_data=_event_data(summary, EventOperation.update),
            message=service.translator.t(
                "mealplan.attendance.closed-notification",
                count=summary.attendee_count,
                meal=service.describe_meal(summary),
            ),
        )


def auto_plan(repos: AllRepositories, service: MealPlanAttendanceService) -> int:
    """Once a week, put the rolling plan's top pick on every empty day. Returns how many were planned."""

    window = service.auto_plan_window()
    if not window:
        return 0

    start, end = window
    settings = service.settings
    rotation = MealPlanRotationService(repos)

    planned = 0
    for entry_type in settings.entry_types:
        request = MealPlanRotationRequest(
            start_date=start, end_date=end, entry_type=entry_type, cooldown_weeks=settings.rotation_cooldown_weeks
        )
        planned += len(rotation.fill(request))

    # The window starts the day after the planning day, which is the day it ran on.
    service.mark_auto_planned(start - timedelta(days=1))
    logger.info("rolling plan filled %d meal(s) for household %s", planned, service.household_id)
    return planned


def _send_reminder_emails(service: MealPlanAttendanceService, summary: MealPlanAttendanceSummary, meal: str) -> None:
    recipients = service.get_reminder_recipients(summary)
    if not recipients:
        return

    email_service = EmailService(locale=service.settings.locale)
    # Without a deadline there is nothing specific to say, so the email's generic text is used.
    body = ""
    if summary.deadline_at:
        body = email_service.translator.t(
            "emails.mealplan-attendance.reminder_body", meal=meal, deadline=service.format_deadline(summary.deadline_at)
        )

    for name, address in recipients:
        try:
            email_service.send_mealplan_attendance_reminder(
                address, f"{email_service.settings.BASE_URL}/household/mealplan/attendance", body
            )
        except Exception:
            logger.exception("failed to send attendance reminder to %s", name or address)


def process_mealplan_attendance() -> None:
    with session_context() as session:
        for group_id, household_id in household_ids_with_attendance_enabled(session):
            try:
                _process_household(session, group_id, household_id)
            except Exception:
                logger.exception("meal attendance upkeep failed for household %s", household_id)
