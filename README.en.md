# Duty service — tracking and distribution of 24-hour shifts

[Русский](README.md) · **English**

A small web application for planning 24-hour duty shifts: it keeps a calendar,
enforces the mandatory recovery day after a shift, grants time off for shifts
on weekends and public holidays, and runs a reproducible draw for a contested day.

Stack: Python 3.11+ (verified on 3.15), FastAPI, SQLite, vanilla JS without a build step.
Visual design is constructivism in a restrained register: a dense grid, paper
background, muted red-brown accent, thin borders and soft shadows; both light
and dark themes are available, plus a RU/EN interface language switch.

## Quick start

```bash
# from the project directory
py -3.15 -m venv .venv
.venv/Scripts/python.exe -m pip install fastapi uvicorn

# demo data: 12 employees, ~3 months of schedule, vacations, comp days
.venv/Scripts/python.exe seed_demo.py --force

# run
DUTY_DB=demo.db .venv/Scripts/python.exe run.py
# open http://127.0.0.1:8000 — the login page opens
```

Demo data creates the accounts (`seed_demo.py` prints their list):

| Login | Password | Role |
|---|---|---|
| `admin` | `admin123` | administrator |
| `kovalev` | `lead123` | teamlead (linked to an employee) |
| `sidorov`, `lebedev`, … | `duty123` | employees |

Without demo data the application starts with an empty `duty.db`; the first
administrator account is created automatically from `DUTY_ADMIN_USER` /
`DUTY_ADMIN_PASSWORD`. If `DUTY_ADMIN_PASSWORD` is not set, a random password is
generated and printed to the console once on first start. **Change the
administrator password right after the first login.**
The database path is set by the `DUTY_DB` environment variable, the port by `PORT`,
the host by `HOST`.

## Rules

* **Recovery day.** After a shift the next day is unavailable to that employee
  (`rest_days`, 1 by default). The recovery day cannot be "filled" with a shift.
* **Minimum interval.** At least `min_gap_days` days must pass between two shifts
  of an employee (2 by default; always ≥ recovery day + 1).
* **Next-day protection.** A shift is not assigned if the employee is already
  scheduled for the next day: otherwise the recovery day would fall on someone's
  shift.
* **Comp day for weekends and holidays.** Every shift on a weekend or holiday
  earns one comp day. The employee picks the date: a working day only, within
  `comp_valid_days` (60) after the shift, free of shifts, recovery days, absences
  and other comp days. Statuses: `ожидает` (pending) → `запланирован` (planned) →
  `использован` (used), or `отказ` (declined). Only «planned» and «used» block a
  shift assignment.
* **Absences.** Vacation, sick leave and business trips exclude an employee from
  distribution for the given period. An absence cannot be added on top of a shift —
  remove the shift first.
* **Holidays.** Belarusian public holidays — 10 non-working days, including
  Radunitsa (computed from the Orthodox Easter). The list is loaded automatically
  on startup for the previous, current and next year; manually deleted dates are
  not added again. The «Заполнить праздники РБ» (Fill in BY holidays) button loads
  or restores the selected year. A holiday counts as a day off.

## Access, roles and accounts

Login is by username and password (`/login`). Passwords are stored as PBKDF2-SHA256
(600,000 iterations) with a salt; the minimum password length is 8 characters.
The session is a signed HMAC cookie `duty_session` (HttpOnly, SameSite=Lax, 12 hours;
`Secure` over HTTPS). Logging out and changing the password revoke all previously
issued sessions of that account. Failed logins are limited:
10 failures within 5 minutes per «IP + login» pair → `429` with `Retry-After`.
Application responses carry `Content-Security-Policy`,
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and
`Permissions-Policy` headers; over HTTPS `Strict-Transport-Security` is added.

| Role | What is available |
|---|---|
| **Employee** | self-service page `/me`: calendar, requests, password change; API `/api/me*` |
| **Teamlead** | schedule, requests, comp days, absences, uncovered days, statistics, settings |
| **Administrator** | all of the above + the «Аккаунты» (Accounts) section and notification settings |

Accounts are created by the administrator in the «Аккаунты» (Accounts) section:
login, password, role, link to an employee (one account per employee), notification
contacts. You cannot delete your own account or leave the system without an active
administrator. An employee without a linked record sees an error — the administrator
must link them to an account in the «Сотрудники» (Employees) section.

## Employee requests

An employee signs in to the `/me` page and marks days in the calendar. The request
goes to the teamlead for approval, the status is visible in the page; a pending
request can be withdrawn.

Request types:

* **«Не могу дежурить» (I cannot work this day)** — a hard constraint. Once approved,
  the employee is excluded from assignments on those days just like during an absence.
* **«Предпочитаю не дежурить» (I prefer not to work this day)** — a soft request.
  Assignment is not forbidden, but auto-distribution skips such an employee if a
  no-extra-load alternative is available. The candidate card shows a warning.

Requests go through approval: `ожидает` (pending) → `согласована` (approved) /
`отклонена` (rejected). A request cannot be approved if the employee already has an
active shift on those days — it must be reassigned first. An employee can withdraw
only a request in the «pending» status. The teamlead and the employee receive
notifications about a new request and about the decision (if notifications are
configured).

Anti-abuse limits:

* current date and forward only, horizon `request_horizon_days` (90 days);
* no more than `request_month_limit` days per month per employee (10, 0 — no limit);
* overlapping requests are not allowed;
* requests from an inactive employee are not accepted.

Lists and decisions are in the «Заявки» (Requests) section; a pending request
counter is visible in the header. In the calendar requests appear as colored chips,
in the day card as an events line, and in the candidates table as a warning. Hard
rules (recovery day, interval, comp days, absences) remain in force regardless of
requests.

## Draw probability model

Load is computed from actual and planned shifts:

```
L = weekdays × 1 + (weekends + holidays) × weekend_weight
```

`weekend_weight` is 1.5 by default — a weekend shift is "more expensive" than a
weekday one. A comp day does not reduce load: the weight of a weekend is already
accounted for by the coefficient.

Among the **checked and available** candidates (the draw runs only among them)
the weight is:

```
w_i = (Lmax − L_i + 1) ^ power
P_i = w_i / Σ w
```

`power` (fairness degree, 2 by default) controls strictness:
1 — soft priority, 3–4 — a strong skew toward less loaded employees.
The employee with the lowest load gets the highest chance, but the choice remains
random. With equal loads the chances are equal.

Example: loads 6.5, 8.0, 9.5. Lmax = 9.5, power = 2:
weights 16, 4, 1 → probabilities 76%, 19%, 5%.

The draw uses `random.Random(seed)`. The seed, the random number `roll`, the table
of weights and probabilities of all candidates, the winner and a SHA-256 seal are
stored in the `draws` table, so the result can be reproduced and verified
independently. In the UI probabilities are recalculated immediately when a checkbox
is toggled — using the same formula.

**Auto-distribution** fills only empty days: each time the employee with the lowest
weighted load is chosen, on a tie — randomly (the seed is stored in the shift note).
It does not touch already occupied days, so running it again is safe.

### Draw proof

Every draw gets a **«Пруф» (Proof)** link (`/proof/{draw_id}`): a page with the
seal, seed, `roll`, the weights and probabilities table and an automatic check.
The `GET /api/proof/{draw_id}` API returns the canonical package (`seed`,
`roll`, candidates, weights, winner), the SHA-256 hash and the verification result.

How it is verified:

1. The package is serialized canonically (JSON, `sort_keys`, compact separators)
   and hashed with SHA-256 — the hash must match the stored one.
2. All weights are positive, the probabilities sum to 1.
3. Independent recomputation: `threshold = roll × Σweights`, then the first
   interval of accumulated weights covering the threshold is found — the winner
   must match the recorded one.

The page shows «ПОДТВЕРЖДЕНО» (CONFIRMED) only if all checks pass;
for old draws without a proof an «архив» (archive) mark is shown. The
«Аудит жеребьёвок» (Draw audit) log on the statistics tab contains the date, mode,
winner, seed, short hash and status; the badge leads to the proof page. The proof
is available to any signed-in account.

### Visual roulette

The **«Рулетка» (Roulette)** button in the schedule header (or in the free-day card)
opens a date picker and a wheel with employees. In the default mode only employees
without vacation, recovery day, broken interval, comp day and approved request are
available. Mode switch:

* **Дежурства за месяц (Duties this month)** — weight `(Mmax − M + 1)^power`, where
  M is the number of the employee's shifts in the month of the target date. Those
  who worked less this month get a larger sector and chance. Overall load and
  weekend weight are not counted here.
* **Равные шансы (Equal chances)** — shifts are not counted at all: everyone has
  weight 1, probability `1 / N`.

The checkbox **«Не блокировать интервал, отгул и заявки — исключать только отпуск и
отсыпной» (Do not block interval, comp day and requests — exclude only vacation and
recovery day)** keeps only absences and the recovery day hard. The remaining
restrictions become deviations: such employees take part in the wheel, deviations
are shown in the participants list, in the result and in the shift note.

If a planned shift is already assigned to the date, the roulette offers to re-roll
the day: after confirmation the old shift is cancelled and a new one is assigned by
the same draw. Re-rolling is forbidden if a comp day has already been planned or
used for the old shift, and for shifts with the status «выполнено» (done) /
«неявка» (no-show).

The sector size equals the probability. The server records the result (`seed`, the
probability table in `draws`), assigns the shift, and the wheel stops on the winner
with an animation; the mode and deviations are written to the shift note. The
roulette result, like a regular draw, gets a proof and a line in the
«Аудит жеребьёвок» (Draw audit) log.

## Days without available employees

Across the planning horizon the system looks for days with no assigned shift where
**not a single** active employee can work (vacation, sick leave, recovery day,
interval, comp day, approved «I cannot»). Such days appear in the
**«Требуют решения» (Require a decision)** section with a breakdown of reasons per
employee and a list of absences and requests awaiting approval.

For each such day the system separately computes a **decision pool**: vacations,
recovery days, intervals and approved requests do not block a candidate but are
shown as deviations. The same coefficient as in the draw is computed over this pool —
weight `(Lmax − L + 1)^power` and probability `weight / Σ weights`.
Candidates are sorted by probability; the assignment card immediately shows the
coefficient, the chance and all deviations of the selected employee. Load here is
computed from actual history, so less loaded employees get a larger coefficient.

The teamlead can:

* **assign a duty officer over the rules** — a reason is required (at least
  5 characters); the assignment, the reason and the author are written to the
  «Назначения поверх правил» (Assignments over the rules) log (`coverage_overrides`),
  the employee receives a notification; warnings about violated rules are shown
  immediately;
* **dismiss a day from control** — with a comment; the day disappears from the list
  but stays in the log and can be returned with the «Вернуть в контроль» (Return to
  control) button.

With notifications enabled, teamleads receive a single email/message about newly
appeared uncovered days; the same day is not notified again (`coverage_alerts`), and
when the day is closed the alert record is deleted.

## Email and Rocket.Chat notifications

Settings → «Уведомления» (Notifications) (administrator only): a master switch,
event flags (new request, request decision, uncovered days), SMTP (server, port,
user, password, sender address, STARTTLS) and the Rocket.Chat webhook, the system
address for links in emails.

Messages are not sent synchronously with the request: they are queued in
`notification_outbox`, a background thread delivers them and records the status
`в очереди` (queued) / `отправлено` (sent) / `ошибка` (error) with the error text.
The «Тест email» (Test email) and «Тест Rocket.Chat» (Test Rocket.Chat) buttons send
a message to the contacts of the current account, «Повторить ошибки» (Retry errors)
returns failed messages to the queue. The send log is visible in the same section.
The SMTP password is not returned by the API — only the `smtp_password_set` flag.

## Interface

* **График (Schedule)** — a month calendar: duty officers, recovery days, comp days,
  absences, requests, holidays, KPIs and the draw log. Clicking a day opens a card:
  shift status change, comp day registration, a candidates table with load,
  probabilities and request warnings, manual assignment, a draw or the **visual
  roulette** with the modes «равные шансы» (equal chances) and
  «дежурства за месяц» (duties this month).
* **Сотрудники (Employees)** — roster, notes (shifts), contacts (email, Rocket.Chat),
  deactivation with history preserved.
* **Заявки (Requests)** — employee requests with filters, approval and rejection.
* **Требуют решения (Require a decision)** — days without available employees:
  reasons, candidates with a coefficient, assignment over the rules, dismissal from
  control and the decisions log (counter in the header).
* **Отгулы (Comp days)** — all comp day entitlements with filters and selection
  deadlines.
* **Отсутствия (Absences)** — vacations, sick leaves, business trips.
* **Статистика (Statistics)** — dashboards on one screen:
  * six KPIs: shifts over the period, average load, horizon coverage,
    weekends covered, no-shows, comp days;
  * **load balance** — the deviation of each employee's weighted load from the
    average (underloaded / overloaded), to see a skew immediately;
  * **employee × month matrix** — a heat map of the number of shifts by months of
    the period;
  * **coverage horizon** — closed, open and dismissed days, a progress bar and a
    list of the nearest problem dates;
  * **weekend share** — who works non-working days more often, a 0–100 % scale;
  * **employee × weekday table** with the number of shifts in cells and a totals row;
  * a detail table: total/weekdays/weekends, weighted load and deviation,
    planned/done/no-shows, comp days, last and next shift;
  * **draw audit** with a proof link and the load formula.
* **Аккаунты (Accounts)** — accounts, roles, links to employees, passwords.
* **Настройки (Settings)** — rules, weights, request limits, the holidays reference,
  notifications and the send log (notifications — administrator only).

### Themes

The theme switch in the header (on the login page — in the top right corner) is
labeled with the target theme: in the light theme it shows «Тёмная» (Dark), in the
dark theme — «Светлая» (Light). The choice is stored in `localStorage`
(`duty-theme`); without an explicit choice the system `prefers-color-scheme` setting
is used. The theme is applied before the page is rendered, so switching causes no
flash; `color-scheme` aligns native controls with it. Printing always uses the light
palette.

### Interface language (RU/EN)

The **EN / RU** button next to the theme switch (on the login page — a separate
button below it) translates the entire interface: the teamlead and administrator SPA,
the employee self-service page, the login and proof pages, including the native
`confirm`/`alert`/`prompt` dialogs and the server error texts in toasts. The choice
is stored in `localStorage` (`duty-lang`); the interface is Russian by default;
`<html lang>` is updated, so screen readers and browser auto-translation see the
correct language.

Translation is a layer on top of the markup (`app/static/i18n.js`): an exact RU→EN
dictionary, rules for dynamic phrases (dates, months, numerals, counters, headings
with names) and a `MutationObserver` that also translates content added after load.
The original Russian text is remembered, so switching back and forth does not
corrupt the markup.

What stays as is: full names, job titles, notes and request reasons entered by users;
the Excel export and CSV; emails and Rocket.Chat messages; the canonical JSON of the
draw package. These are data and external artifacts, not interface elements —
translating them would distort reporting.

CSV export (UTF-8 BOM, `;` separator) opens in Excel with a Russian locale.
The **«Excel для печати» (Excel for printing)** button on the schedule page exports
an XLSX with two sheets:

* **«ФИО-Дата» (Name-Date)** — a matrix: rows are employees, columns are the dates
  of the period, a `Д` at the intersection means a shift. Weekend columns are filled
  pink, holiday columns yellow; at the end — «Всего» (Total) and «Вых.» (Weekends).
  The first column and the header are frozen and repeated on every page when printed;
* **«Список» (List)** — a detailed schedule by dates: duty officer, status,
  comp day, note.

Print layout: A4 landscape, headers and footers, signature lines. The XLSX generator
is written on the standard library (`zipfile` + OOXML), no external dependencies are
needed.

## Tests

```bash
.venv/Scripts/python.exe -m pytest
node --test tests/test_i18n.mjs   # dictionary and translation rules
```

Coverage: compatibility rules, recovery days, holidays, probabilities, draw
reproducibility and proof verification (hash, sum of probabilities, independent
recomputation of the winner, archived draws without a proof), auto-distribution,
comp days, employee requests, limits and approval, login and roles (RBAC), passwords,
uncovered days and assignments over the rules, the candidate pool with a coefficient,
the weekday matrix, statistics dashboards, the schedule Excel export, the
notification queue, roulette modes (equal chances and weights by duties this month),
the relaxed mode (vacation and recovery day only), re-rolling an occupied day, CSV
formula injection protection, security headers, login attempt limiting, session
revocation, the minimum password length, the presence of the RU/EN switch on all
pages, dictionary completeness and translation of roulette dates and phrases —
**44 tests** in pytest plus 5 translation checks in Node.

## Structure

```
app/
  main.py       FastAPI, REST API, RBAC middleware, validation
  engine.py     rules, loads, probabilities, auto-distribution, comp days
  db.py         SQLite schema, settings, transactions
  security.py   passwords, signed sessions
  notifier.py   email/SMTP and Rocket.Chat queue
  xlsx.py       XLSX generator for printing (zip + OOXML, no dependencies)
  holidays.py   Belarusian holidays and Orthodox Easter
  proofs.py     canonical package, SHA-256 and draw verification
  static/       index.html, app.js — teamlead/admin SPA;
                my.html, my.js — employee self-service; login.html, login.js;
                theme.js — light/dark theme; i18n.js — RU/EN switch;
                style.css — constructivism
run.py          uvicorn entry point
seed_demo.py    demo database and accounts
tests/          pytest; test_i18n.mjs — dictionary checks in Node
```

## Main endpoints

| Method | Path | Purpose | Access |
|---|---|---|---|
| POST | `/api/auth/login`, `/api/auth/logout` | sign in and out | everyone |
| GET | `/api/auth/me`, POST `/api/auth/password` | current user, password change | everyone |
| GET | `/api/me`, POST/DELETE `/api/me/requests[/{id}]` | employee page and requests | employee |
| GET | `/api/schedule?month=YYYY-MM` | calendar, loads, log | teamlead/admin |
| GET | `/api/candidates?date=` | availability, loads, probabilities | teamlead/admin |
| POST | `/api/duties`, PATCH/DELETE `/api/duties/{id}` | manual shift | teamlead/admin |
| GET | `/api/roulette?date=&relaxed=` | participants and probabilities of the two roulette modes; `relaxed=1` keeps only vacation and the recovery day hard | teamlead/admin |
| POST | `/api/draw` | draw/roulette (`date`, `candidate_ids`, `seed`, `mode`: `load`\|`equal`\|`month`, `relaxed`, `replace`); the response contains `drawId`, `roll`, `proofHash`, `proofUrl`, `deviations` | teamlead/admin |
| GET | `/api/proof/{draw_id}` | proof package, hash and verification result | all signed in |
| GET | `/proof/{draw_id}` | draw proof page | all signed in |
| POST | `/api/auto-plan` | fill empty days | teamlead/admin |
| GET | `/api/comps`, PUT `/api/comps/{duty_id}` | comp days | teamlead/admin |
| GET/POST/DELETE | `/api/absences` | absences | teamlead/admin |
| GET/POST/DELETE | `/api/holidays`, POST `/api/holidays/seed` | holidays | teamlead/admin |
| GET | `/api/stats` | statistics and dashboards (KPI, balance, months, coverage, weekend share, weekday matrix, draw audit) | teamlead/admin |
| GET | `/api/export?month=`, `/api/export/schedule.xlsx?month=` | CSV and XLSX schedule for printing | teamlead/admin |
| GET/PUT | `/api/settings` | rules and notifications | teamlead/admin* |
| GET | `/api/requests`, PATCH/DELETE `/api/requests/{id}` | requests and decisions | teamlead/admin |
| GET | `/api/coverage` | uncovered days, logs | teamlead/admin |
| POST/DELETE | `/api/coverage/{day}/dismiss`, `/api/coverage/{day}` | dismiss/return a day | teamlead/admin |
| POST | `/api/coverage/{day}/assign` | assign over the rules | teamlead/admin |
| GET/POST/PATCH/DELETE | `/api/users[/{id}]` | accounts | admin |
| GET/POST | `/api/notifications[/test|/retry]` | log and channel checks | admin |
| GET | `/login`, `/me`, `/` | login, self-service, SPA pages | — |

\* notification settings and reading the send log — administrator only.

## Limitations

A single job group (unit). Authentication is local (login/password, no external SSO
or LDAP); sessions last 12 hours. Login attempts are limited to 10 failures per 5
minutes per IP + login pair; when publishing to the internet still put a
reverse proxy with rate limiting and HTTPS in front (the session cookie must then
travel over TLS only). Notifications are sent by a background thread without
scheduled retries: failed messages stay in the log and are retried with a button.
SQLite is sufficient for hundreds of employees and several years of schedule; it can
easily be swapped for PostgreSQL if needed.
