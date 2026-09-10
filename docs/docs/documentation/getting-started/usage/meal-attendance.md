# Meal Attendance

Meal attendance turns the meal planner into a commitment flow. Everyone in the household
says whether they are eating along, a deadline closes the day, and the recipes are then
scaled to the number of confirmations so the shopping list reflects what will actually be
cooked.

It is off by default and only affects the meal types you opt in to, so the rest of the
planner keeps working exactly as before.

## How it works

1. **Plan the meals.** Nothing changes here — use the meal planner as usual.
2. **Everyone answers.** Each participant, and any guests they bring, confirms or declines.
   Until they answer, their default profile counts.
3. **The deadline closes the day.** Once the cutoff passes, the answers are frozen and can
   no longer be changed without reopening the meal.
4. **Portions are calculated.** The recipe is scaled by `confirmations ÷ recipe servings`.
   A recipe for four with seven confirmations comes out at 1.75×.
5. **The shopping list is filled** from the final numbers.

## Participants

A participant is either a household member or a guest.

- **Members** are pulled in with *Add household members*, and eat along by default.
- **Guests** — a partner, a child, a visitor — hang off the member they belong to, and do
  *not* eat along by default. That member answers for them.

Anyone can also add extra unnamed guests to a single meal when someone brings company.

Household managers can answer for everybody; everyone else answers only for themselves and
their own guests.

## Deadlines

Three modes, set per household:

| Mode | Behaviour |
| --- | --- |
| **A fixed weekday** | The last cutoff before the meal closes it. With Thursday 20:00, the Sunday, Monday and Tuesday that follow all close at the same moment — one deadline for the whole week. |
| **A number of days before each meal** | Every meal closes the same number of days before it is served. |
| **Per meal only** | No automatic deadline. A cutoff can still be set on an individual meal. |

The cutoff time is read in the household's configured time zone, so it survives daylight
saving changes. A deadline set on an individual meal always wins over the household rule.

With **Close automatically** switched on, an hourly task locks meals whose deadline has
passed. Locking freezes the answers into real records, so a meal that is already closed
does not change if somebody later edits their default profile or their absences.

Reopening a closed meal always sets a fresh deadline — 24 hours by default. Without one,
the household rule would put the cutoff back in the past and the meal would close again
immediately.

## Absences

Holidays, business trips and weekends elsewhere are recorded as date ranges. Somebody who
is away is counted as declined for any meal in that range, whatever they clicked, and the
meal shows why. Everyone manages their own absences; household managers can manage
everybody's.

## Reminders

When reminders are enabled, an hourly task emails everyone who still owes an answer as the
deadline approaches, and each meal is only reminded about once. Two event types,
`mealplan_attendance_reminder` and `mealplan_attendance_closed`, are also published to the
event bus, so they can be forwarded to Apprise notifiers or webhooks.

Reminders need SMTP to be configured — see
[Backend Configuration](../installation/backend-config.md).

## Shopping list

*Add to shopping list* takes every planned meal in the displayed week and adds its recipe,
scaled to the confirmations. By default only closed meals are included, since the portions
of an open meal can still change. Meals without a recipe are skipped and the reason is
reported back.

## Rolling plan

The API also exposes recipe suggestions and a rotation endpoint that ranks candidates for
the open slots in a date range:

- recipes marked as favourites by household members rank higher,
- recipes cooked recently are held back until their cooldown has passed,
- and recipes last chosen by whoever has been deciding most are pushed down, so the same
  person does not end up picking every week.

Each candidate comes back with the reasons behind its score, so the ranking can be
explained rather than just trusted.
