"""
Hourly upkeep for the meal attendance module.

Two jobs, in this order: nag the people who still owe an answer, then close the meals
whose deadline has passed. Doing it the other way round would lock a meal in the same
run that was supposed to remind people about it.
"""

from pydantic import UUID4
from sqlalchemy.orm import Session

from mealie.core.root_logger import get_logger
from mealie.db.db_setup import session_context
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_mealplan_attendance import household_ids_with_attendance_enabled
from mealie.schema.meal_plan.attendance import MealPlanAttendanceSummary
from mealie.schema.user.user import DEFAULT_INTEGRATION_ID
from mealie.services.email.email_service import EmailService
from mealie.services.event_bus_service.event_bus_service import EventBusService
from mealie.services.event_bus_service.event_types import (
    EventMealplanAttendanceData,
    EventOperation,
    EventTypes,
)
from mealie.services.household_services.mealplan_attendance import MealPlanAttendanceService

logger = get_logger()


def _describe(summary: MealPlanAttendanceSummary) -> str:
    name = summary.recipe_name or summary.title or summary.entry_type.value
    return f"{name} on {summary.date.isoformat()}"


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

    for summary in service.collect_due_reminders():
        description = _describe(summary)
        _send_reminder_emails(service, summary, description)

        event_bus.dispatch(
            integration_id=DEFAULT_INTEGRATION_ID,
            group_id=group_id,
            household_id=household_id,
            event_type=EventTypes.mealplan_attendance_reminder,
            document_data=_event_data(summary, EventOperation.info),
            message=f"{summary.pending_response_count} answer(s) still missing for {description}",
        )

    for summary in service.close_expired_meals():
        event_bus.dispatch(
            integration_id=DEFAULT_INTEGRATION_ID,
            group_id=group_id,
            household_id=household_id,
            event_type=EventTypes.mealplan_attendance_closed,
            document_data=_event_data(summary, EventOperation.update),
            message=f"Attendance closed for {_describe(summary)} with {summary.attendee_count} confirmation(s)",
        )


def _send_reminder_emails(
    service: MealPlanAttendanceService, summary: MealPlanAttendanceSummary, description: str
) -> None:
    recipients = service.get_reminder_recipients(summary)
    if not recipients:
        return

    email_service = EmailService()
    deadline = summary.deadline_at.isoformat() if summary.deadline_at else "soon"
    body = f"Are you eating along? {description}. Please answer by {deadline}."

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
