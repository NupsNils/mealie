# Easy Setup

Kurzanleitung für diesen Mealie-Fork. Er erweitert Mealie um das Modul
**Mahlzeiten-Teilnahme**: jeder sagt zu oder ab, nach Ablauf einer Frist wird der Tag
gesperrt, und die Rezepte werden automatisch auf die Zusagen hochgerechnet.

Die vollständige Beschreibung des Moduls steht in
[`docs/docs/documentation/getting-started/usage/meal-attendance.md`](docs/docs/documentation/getting-started/usage/meal-attendance.md).

---

## Variante A: Einfach benutzen (Docker)

Der schnellste Weg. Vorausgesetzt sind Docker und Docker Compose.

```bash
git clone https://github.com/NupsNils/mealie.git
```

```bash
cd mealie/docker && docker compose -f docker-compose.yml -p mealie up -d --build
```

Der erste Build dauert einige Minuten. Danach läuft Mealie auf
**<http://localhost:9091>**.

Erster Login:

| | |
|---|---|
| E-Mail | `changeme@example.com` |
| Passwort | `MyPassword` |

**Passwort direkt ändern.** Die Registrierung ist in dieser Compose-Datei
absichtlich aus (`ALLOW_SIGNUP: "false"`); weitere Personen legst du unter
*Einstellungen → Haushalt → Mitglieder* an.

Stoppen und Daten behalten:

```bash
cd mealie/docker && docker compose -p mealie down
```

Die Datenbank liegt im Docker-Volume `mealie-data` und übersteht einen Neustart.

---

## Variante B: Weiterentwickeln

Empfohlen unter Linux oder im VS-Code-Devcontainer. Gebraucht werden
[Task](https://taskfile.dev), [uv](https://docs.astral.sh/uv/) und Node mit pnpm.

```bash
git clone https://github.com/NupsNils/mealie.git && cd mealie && task setup
```

Dann in zwei Terminals:

```bash
task py
```

```bash
task ui
```

Backend läuft auf Port 9000, Frontend auf **<http://localhost:3000>**. Das Frontend
spricht das Backend über `API_URL` an (Standard `http://localhost:9000`).

Nützliche Befehle:

| Befehl | Zweck |
|---|---|
| `task py:check` | Formatieren, Linten, Typen prüfen, Tests |
| `task ui:check` | Frontend linten und testen |
| `task dev:generate` | TypeScript-Typen und Schema-Exporte neu erzeugen |
| `task py:migrate -- "beschreibung"` | Neue Alembic-Migration anlegen |

**Nach jeder Änderung an einem Pydantic-Schema `task dev:generate` laufen lassen** —
die Dateien unter `frontend/app/lib/api/types/` sind generiert und werden nicht von
Hand bearbeitet.

---

## Erste Schritte im Modul

Das Modul ist bewusst **standardmäßig aus**, damit sich am gewohnten Essensplaner
nichts ändert. So schaltest du es ein:

1. **Einschalten.** Sidebar → *Meal Attendance* → Zahnrad oben rechts. Dort *Enable
   meal attendance* setzen und auswählen, für welche Mahlzeitarten geantwortet werden
   soll (Standard: nur Abendessen).

2. **Frist festlegen.** Auf derselben Seite. Für den klassischen Fall „bis Donnerstag
   20 Uhr für die kommende Woche": Modus *A fixed weekday*, Tag *Donnerstag*, Uhrzeit
   *20:00*, Zeitzone *Europe/Berlin*. Sonntag, Montag und Dienstag der Folgewoche
   teilen sich dann eine Frist.

3. **Teilnehmer anlegen.** Sidebar → *Meal Attendance* → Personen-Symbol →
   *Add household members*. Danach mit *Add guest* die Partner hinzufügen. Merke:
   Haushaltsmitglieder essen standardmäßig **mit**, Gäste standardmäßig **nicht**.

4. **Mahlzeiten planen** wie gewohnt im Essensplaner.

5. **Antworten einsammeln.** Auf der Teilnahme-Seite hakt jeder für sich und seine
   Gäste ab. Oben stehen die Zusagen, der Umrechnungsfaktor und wie viele Antworten
   noch fehlen.

6. **Einkaufsliste füllen.** Einkaufswagen-Symbol oben rechts. Standardmäßig werden
   nur bereits gesperrte Tage übernommen, weil sich bei offenen Tagen die Portionen
   noch ändern können.

Für Erinnerungs-Mails muss SMTP konfiguriert sein — die Variablen stehen
auskommentiert in `docker/docker-compose.yml`. Ohne SMTP funktioniert alles andere
normal, es werden nur keine Mails verschickt.

---

## Wenn etwas klemmt

**Windows, `pip`/`uv` bricht bei `python-ldap` ab.** Das Paket braucht den Microsoft
C++ Build Tools Compiler. Wer LDAP nicht benutzt, kann es überspringen:

```bash
uv sync --frozen --no-install-package python-ldap
```

Danach fehlt allerdings das Modul `ldap`, und `mealie.app` lässt sich nicht
importieren. Für lokale Tests hilft ein Stub unter
`.venv/Lib/site-packages/ldap/`. Bequemer ist der Devcontainer oder WSL.

**Windows, `pnpm` nicht gefunden.** `corepack enable` braucht Administratorrechte.
Ohne die geht es auch direkt:

```bash
corepack pnpm install
```

**Windows, `task dev:generate` scheitert.** Der Generator ruft `json2ts` auf, das
global installiert sein muss:

```bash
npm install -g json-schema-to-typescript
```

Zusätzlich `PYTHONUTF8=1` setzen, sonst liest der Generator Quelldateien in der
falschen Zeichenkodierung.

**Tests scheinen zu hängen.** Alle Integrationstests teilen sich eine
SQLite-Datenbank. Läuft versehentlich mehr als ein `pytest` gleichzeitig, blockieren
sich die Läufe gegenseitig. Erst alle Prozesse beenden, `tests/.temp` löschen, dann
genau einen Lauf starten.

**Frist wirkt falsch.** Die Uhrzeit wird in der eingestellten Zeitzone gelesen, nicht
in der des Servers. Steht dort noch `UTC`, verschiebt sich der Abschluss gegenüber
der Erwartung.

---

## Was noch offen ist

- Die Migration ist gegen SQLite geprüft, **noch nicht gegen PostgreSQL**.
- Die TypeScript-Typen wurden unter Windows erzeugt und anschließend an den
  Projektstil angeglichen. Vor einem Pull Request einmal `task dev:generate` im
  Devcontainer laufen lassen, damit die maßgebliche Fassung entsteht.
