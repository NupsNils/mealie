# Übergabe: Modul „Mahlzeiten-Teilnahme" (Meal Attendance)

**Stand: 2026-09-09, 16:20 Uhr — 16 von 19 Schritten fertig.**

Wenn du hier weitermachst: lies diese Datei, dann arbeite die offenen Schritte 17–19 unten ab.

## Worum es geht

Fork-Erweiterung von Mealie nach der Anforderung: Mahlzeiten planen → Teilnahmephase mit
Frist → nach Fristablauf gesperrt → Portionen automatisch aus den Zusagen hochrechnen →
Einkaufsliste nur mit den endgültigen Portionen. Dazu Erinnerungen, Standardprofile,
Abwesenheiten, „wer kocht / wer kauft ein" und eine rollierende Planung mit Favoriten,
Cooldown und fairer Rotation.

Grundprinzip: **eigenständiges Modul.** Keine bestehende Rezepttabelle wurde geändert.
Alles liegt in neuen Tabellen, `mealplan_entry_details` ist eine 1:1-Seitentabelle zu
`group_meal_plans`. Dadurch bleibt der Fork gegenüber Upstream-Mealie mergefähig.

## Fertig (1–16)

| # | Schritt | Dateien |
|---|---|---|
| 1 | SQLAlchemy-Modelle (6 neue Tabellen) | `mealie/db/models/household/mealplan_attendance.py` |
| 2 | Beziehungen in bestehenden Modellen | `household.py`, `mealplan.py`, `users.py`, `recipe/recipe.py` (nur ORM, keine Spalten) |
| 3 | Alembic-Migration, up **und** down geprüft | `mealie/alembic/versions/2026-09-09-15.39.14_51f59d2075d9_add_meal_attendance_module.py` |
| 4 | Pydantic-Schemas | `mealie/schema/meal_plan/attendance.py` |
| 5 | Repositories + Registrierung | `mealie/repos/repository_mealplan_attendance.py`, `repository_factory.py` |
| 6 | Attendance-Service (Fristen, Portionen, Sperre, Einkaufsliste) | `mealie/services/household_services/mealplan_attendance.py` |
| 7 | Rotations-/Vorschlags-Service | `mealie/services/household_services/mealplan_rotation.py` |
| 8–11 | API-Controller + Router-Registrierung | `mealie/routes/households/controller_mealplan_attendance.py`, `routes/households/__init__.py` |
| 12 | Event-Typen `mealplan_attendance_reminder` / `_closed` + Notifier-Spalten | `event_types.py`, `group_events.py`, `db/models/household/events.py` |
| 13 | Scheduler-Task (stündlich: Erinnern, dann Sperren) | `mealie/services/scheduler/tasks/mealplan_attendance.py`, registriert in `app.py` |
| 14 | Erinnerungs-Mail + `emails.mealplan-attendance.*` | `services/email/email_service.py`, `mealie/lang/messages/en-US.json` |
| 15 | Codegen: TS-Typen + Schema-Exporte | `frontend/app/lib/api/types/meal-plan.ts`, `household.ts`, `mealie/schema/meal_plan/__init__.py` |
| 16 | Frontend-API-Client | `frontend/app/lib/api/user/household-mealplan-attendance.ts`, eingehängt in `client-user.ts` |

Nebenbei behoben: `dev/code-generation/gen_ts_types.py` baute Modulnamen mit POSIX-Separatoren
und lief deshalb unter Windows nicht. Jetzt über `Path.parts`.

## Offen (17–19)

### 17. Frontend-Seiten
- `frontend/app/pages/household/mealplan/attendance.vue` — das Wochen-Raster:
  Zeilen = Teilnehmer (Person + ihre Gäste/Partner), Spalten = Mahlzeiten der Woche,
  Häkchen zum Zu-/Absagen. Dazu je Mahlzeit: Countdown bis zur Frist, Schloss-Symbol wenn
  gesperrt, `attendeeCount` und der berechnete `scaleFactor` („Rezept für 4 → 7 Portionen").
  Datenquelle: `api.mealplanAttendance.getOverview(start, end)`; Schreiben über
  `setAttendanceBulk`, damit man für sich **und** den Partner in einem Rutsch antworten kann.
- `frontend/app/pages/household/mealplan/participants.vue` — Teilnehmer und Gäste anlegen,
  Standardprofil (`defaultAttending`) setzen, Abwesenheiten pflegen.
  Beim ersten Aufruf `api.mealplanAttendance.participants.syncFromUsers()` anbieten.
- Einstellungen: entweder ein Abschnitt in `frontend/app/pages/household/mealplan/settings.vue`
  oder eine eigene Seite. Felder: `enabled`, `deadlineMode`, `deadlineWeekday`, `deadlineTime`,
  `timezone`, `autoLock`, `reminderEnabled`, `reminderHoursBefore`, `entryTypes`.
- Composable `frontend/app/composables/use-mealplan-attendance.ts` nach dem Muster von
  `use-group-mealplan.ts`.
- Navigation: Einträge in der Sidebar unter „Mealplan" ergänzen.

### 18. Übersetzungen
Neuer Block `meal-plan.attendance.*` in `frontend/app/lang/messages/en-US.json`.
**Nur en-US anfassen** — alle anderen Locales laufen über Crowdin (siehe AGENTS.md).

### 19. Integrationstests
`tests/integration_tests/user_household_tests/test_mealplan_attendance.py`.
Muster: `tests/integration_tests/user_household_tests/test_group_mealplan.py`.
Wichtig: **Testklassen müssen auf `Tests` enden** (`python_classes = '*Tests'` in
`pyproject.toml`), sonst sammelt pytest nichts ein.

Abzudecken:
- Teilnehmer anlegen (Person + Partner als Gast), Standardprofile greifen in der Übersicht.
- Zusagen setzen → `attendeeCount` und `scaleFactor` stimmen.
- Abwesenheit über den Mahlzeit-Tag → Teilnehmer wird als abwesend und abgesagt gezählt.
- Nach `lock` liefert ein Schreibversuch **423 Locked**.
- `unlock` ohne `deadline_at` öffnet für 24 h und sperrt nicht sofort wieder.
- `POST /households/mealplan-attendance/shopping-list` mit `only_locked=true` überspringt
  offene Mahlzeiten und trägt die gesperrten mit dem berechneten Faktor ein.

## Wichtige Design-Entscheidungen (damit nichts umgebaut wird)

- **Lesen schreibt nie.** Die Übersicht wird aus Teilnehmern, deren Standardprofil,
  Abwesenheiten und den tatsächlich gespeicherten Antworten projiziert. Zeilen entstehen erst,
  wenn jemand antwortet oder wenn gesperrt wird — beim Sperren wird die Projektion in echte
  Zeilen eingefroren, damit gesperrte Mahlzeiten stabil bleiben.
- **Frist `weekly`:** der letzte konfigurierte Wochentag **strikt vor** dem Mahlzeitentag.
  Mit „Donnerstag 20:00" teilen sich Sonntag, Montag und Dienstag der Folgewoche eine Frist —
  genau das gewünschte Verhalten. Getestet in `tests/unit_tests/services_tests/test_mealplan_attendance.py`.
- **`unlock` setzt immer eine neue Frist** (Standard: +24 h). Sonst läge die aus den
  Haushaltseinstellungen abgeleitete Frist wieder in der Vergangenheit und die Mahlzeit
  würde beim nächsten Request sofort erneut sperren.
- **Abwesenheit schlägt die Antwort.** Wer im Urlaub ist, zählt nicht mit; die Übersicht
  zeigt `isAbsent` samt Grund, damit die Oberfläche das erklären kann.
- Favoriten (❤) wurden **nicht** neu gebaut — Mealie hat `UserToRecipe.is_favorite`
  (`repos.user_ratings`). Der Cooldown kommt aus der bestehenden Mealplan-Historie.

## Umgebung (nur relevant, wenn du wieder unter Windows arbeitest)

Auf dem alten Rechner waren drei Behelfe nötig, die **nicht** im Repo liegen:

1. `python-ldap` lässt sich ohne MSVC nicht bauen → `uv sync --frozen --no-install-package python-ldap`
   und ein Stub-Modul unter `.venv/Lib/site-packages/ldap/`, damit `mealie.app` importierbar ist.
2. `pnpm` über `corepack pnpm ...` (globales `corepack enable` scheitert an fehlenden Rechten).
3. `json2ts` global via npm mit benutzereigenem Prefix, für die TS-Codegen.

Unter Linux / im Devcontainer entfällt das alles — dort einfach `task setup`.

**Vor einem PR:** `task dev:generate` im Devcontainer laufen lassen. Die TS-Typen wurden hier
unter Windows erzeugt und anschließend an den Projektstil angeglichen (die lokale
json2ts-Version fügt zusätzliche Index-Signaturen ein). Inhaltlich stimmen sie, aber die
maßgebliche Fassung sollte aus dem Devcontainer kommen.

## Prüfstand beim Abbruch

- `ruff check mealie/` → sauber (die 10 Meldungen in `tests/` sind Altbestand, nicht aus diesem Modul).
- `pytest tests/unit_tests/services_tests/test_mealplan_attendance.py` → 13 grün.
- Migration up/down/up gegen SQLite geprüft, `alembic check` meldet keine Abweichung zum Modell.
- **Gegen PostgreSQL ist die Migration noch nicht getestet** — vor dem PR nachholen.
- ESLint über den neuen API-Client → sauber.
