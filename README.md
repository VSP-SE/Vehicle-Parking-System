<div align="center">

# Vehicle Parking System

**Book a slot before you leave, park when you arrive, pay at the gate.**

A full parking-lot platform for drivers, gate attendants and lot administrators,<br>
with race-safe slot allocation and a machine-learning availability forecast.

[![Test Plan](https://img.shields.io/badge/Test%20Plan-49%20of%2051%20Pass%20%C2%B7%200%20Fail-2E7D32?style=for-the-badge&labelColor=66BB6A)](docs/part-3/system-validation-report.md)
[![Tests](https://img.shields.io/badge/Tests-771%20Passing-1B5E20?style=for-the-badge&labelColor=43A047&logo=pytest&logoColor=FFFFFF)](docs/part-3/unit-test-report.md)
[![Coverage](https://img.shields.io/badge/Coverage-95.94%25%20Line%20%C2%B7%2091.01%25%20Branch-00695C?style=for-the-badge&labelColor=26A69A)](docs/part-3/code-coverage-report.md)
[![Load](https://img.shields.io/badge/Load-200%20Sessions%20%C2%B7%200%20Failures-1565C0?style=for-the-badge&labelColor=42A5F5)](docs/part-3/system-validation-report.md)
[![Accessibility](https://img.shields.io/badge/Accessibility-WCAG%202.1%20AA%20%C2%B7%200%20Violations-6A1B9A?style=for-the-badge&labelColor=AB47BC)](docs/part-3/system-validation-report.md)
[![Allocation](https://img.shields.io/badge/Allocation-Race--Safe%20%C2%B7%20Advisory%20Lock-B71C1C?style=for-the-badge&labelColor=EF5350)](vps/reservations/services.py)
[![Forecast](https://img.shields.io/badge/Forecast-FastAPI%20%C2%B7%20scikit--learn-E65100?style=for-the-badge&labelColor=FF9800&logo=fastapi&logoColor=FFFFFF)](forecast/)
[![Language](https://img.shields.io/badge/Language-Python%203.12-1C1C1C?style=for-the-badge&labelColor=424242&logo=python&logoColor=FFD700)](requirements.txt)
[![Framework](https://img.shields.io/badge/Framework-Django%205.2-092E20?style=for-the-badge&labelColor=2E7D32&logo=django&logoColor=FFFFFF)](requirements.txt)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%2016-1A237E?style=for-the-badge&labelColor=5C6BC0&logo=postgresql&logoColor=FFFFFF)](compose.yaml)
[![CI](https://img.shields.io/badge/CI-Lint%20%C2%B7%20Tests%20%C2%B7%20Security-512DA8?style=for-the-badge&labelColor=9575CD&logo=githubactions&logoColor=FFFFFF)](.github/workflows/ci.yml)
[![Team](https://img.shields.io/badge/Team-10%20%C2%B7%20PES%20University-B8860B?style=for-the-badge&labelColor=FFD54F)](#team)

[Features](#features) · [Screenshots](#screenshots) · [Architecture](#architecture) · [Quick start](#quick-start) · [Testing](#testing) · [Docs](#documentation) · [Team](#team)

</div>

---

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/images/search-result.png" alt="Driver slot search with availability forecast"></td>
    <td width="50%"><img src="docs/images/occupancy.png" alt="Live lot occupancy dashboard"></td>
  </tr>
  <tr>
    <td align="center"><b>Find parking</b><br><sub>Free slots for your vehicle and time, with the chance one is still free when you arrive</sub></td>
    <td align="center"><b>Live occupancy</b><br><sub>Free, reserved, occupied and blocked slots per lot and slot type</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/gate.png" alt="Gate attendant console"></td>
    <td width="50%"><img src="docs/images/revenue.png" alt="Revenue report with CSV export"></td>
  </tr>
  <tr>
    <td align="center"><b>Gate console</b><br><sub>Check-in, check-out and walk-ins from one screen</sub></td>
    <td align="center"><b>Revenue report</b><br><sub>Charges, payments by method and unpaid totals, exportable as CSV</sub></td>
  </tr>
</table>

<sub>Screenshots taken from the seeded demo data set (`seed_demo_data --seed 2026`).</sub>

## Features

<table>
<tr>
<th width="33%">🚗 Drivers</th>
<th width="33%">🚧 Gate attendants</th>
<th width="33%">🛠️ Lot administrators</th>
</tr>
<tr valign="top">
<td>

- Register, sign in and reset a password by email
- Add vehicles (car, two-wheeler, EV)
- Search free slots by lot, vehicle and time
- See the forecast chance of a free slot on arrival
- Book with a confirmation page, email and booking reference
- Cancel bookings
- Booking history with any unpaid balance

</td>
<td>

- One-screen gate console
- Check in booked vehicles, with automatic reallocation if the slot is still occupied
- Register walk-in vehicles
- Check out with parking and overstay charges
- Take payments by cash, UPI or card
- Print receipts
- Correct entry and exit times after an outage

</td>
<td>

- Create, edit, archive and restore lots
- Tariffs per slot type
- Block a slot for a period; its bookings move elsewhere
- Live occupancy across lots
- Revenue and occupancy reports with CSV export
- Search the append-only audit log
- Waive charges, with a required written reason
- Staff accounts and accessible-parking permits

</td>
</tr>
</table>

### Booking rules

| Rule | Value |
|---|---|
| Booking length | 30 minutes to 24 hours |
| How far ahead | Up to 7 days |
| Open bookings per driver | At most 2, and none while a charge is unpaid |
| No-show | Expires 15 minutes after the start time, Rs 50.00 charge, slot freed |
| Late cancellation | Within 60 minutes of the start, Rs 30.00 charge |
| Overstay | Billed at 1.5x the tariff after a 10-minute grace period |
| Slot types | Standard, Two-wheeler, Electric vehicle, Accessible |

### Under the hood

- **Race-safe allocation.** Concurrent bookings for the same lot are serialised with a PostgreSQL advisory lock, so two drivers never get the same slot and nobody is refused while a slot is free. A `btree_gist` exclusion constraint also stops overlapping bookings on a slot at the database level.
- **Availability forecast.** A separate FastAPI service predicts the chance a suitable slot is free at arrival and labels it Low, Medium or High. It retrains weekly from completed stays. If it does not answer within 2 seconds, search carries on without it.
- **Audit trail.** Privileged staff actions are written to an append-only log that cannot be edited or deleted.
- **Role-based access.** Each page and action checks the signed-in user's role.

## Architecture

```mermaid
flowchart LR
    U(["Drivers · Attendants · Admins"]) --> W

    subgraph Compose["docker compose"]
        W["<b>web</b><br/>Django 5.2 on Gunicorn<br/>:8000"]
        S["<b>scheduler</b><br/>no-show expiry and<br/>notifications, every 60 s"]
        F["<b>forecast</b><br/>FastAPI · scikit-learn<br/>:8001"]
        T["<b>forecast-trainer</b><br/>retrains weekly"]
        D[("<b>db</b><br/>PostgreSQL 16<br/>btree_gist")]
        M[/"forecast_models<br/>volume"/]
    end

    W <--> D
    S --> D
    W -->|"GET /v1/forecast<br/>2 s timeout"| F
    T -->|"read-only role<br/>forecast_ro"| D
    T --> M
    M --> F
```

| Service | What it does |
|---|---|
| `web` | Runs migrations, then serves the Django app with Gunicorn (`GUNICORN_WORKERS`, default 8) |
| `scheduler` | Same image as `web`. Runs `expire_no_shows` and `send_reservation_notifications` every 60 seconds |
| `forecast` | Serves the latest trained model over HTTP |
| `forecast-trainer` | Trains at start-up and then weekly, through a read-only database role |
| `db` | PostgreSQL 16, initialised by the scripts in `docker/postgres/init/` |

UML diagrams (use case, components, data model, sequences, reservation states) are in [`docs/part-1/diagrams/`](docs/part-1/diagrams/).

## Tech stack

| Layer | Technology |
|---|---|
| Web app | Python 3.12, Django 5.2.18, Django REST Framework 3.18.3 |
| Frontend | Server-rendered Django templates with HTMX |
| Database | PostgreSQL 16 with `btree_gist`, psycopg 3 |
| Serving | Gunicorn 26.2.0, Docker Compose |
| Forecast | FastAPI 0.162.0, Uvicorn 0.54.0, scikit-learn 1.9.1, joblib |
| Quality | pytest, pytest-django, pytest-cov, ruff, pip-audit, Gitleaks, GitHub Actions |

## Quick start

### With Docker Compose (recommended)

```sh
git clone https://github.com/VSP-SE/Vehicle-Parking-System.git
cd Vehicle-Parking-System
cp .env.example .env        # then set DJANGO_SECRET_KEY and the passwords
docker compose up --build
```

Open <http://localhost:8000>. <http://localhost:8000/healthz> reports the app and database status.

Load the demo data (a 500-slot lot, 120 drivers and 30 days of bookings):

```sh
docker compose exec web python manage.py seed_demo_data --seed 2026
```

> [!NOTE]
> Gunicorn does not reload on code changes. Run `docker compose restart web`, or use `python manage.py runserver` on the host while developing. `docker compose down -v` deletes the database volume.

### Without Docker

You need Python 3.12 or newer and a local PostgreSQL 16 database.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # edit with your local values
set -a; source .env; set +a # Django reads exported variables, not .env itself
python manage.py migrate
python manage.py runserver
```

<details>
<summary><b>Environment variables</b></summary>

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key (required) |
| `DJANGO_DEBUG` | `True` for local development only |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Database name and credentials |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Database host and port for Django on the host (Compose uses `db`) |
| `FORECAST_DB_PASSWORD` | Password for the trainer's read-only `forecast_ro` role, set before the volume is first created |
| `FORECAST_URL` | Forecast service URL for Django on the host; empty runs without a forecast |
| `GUNICORN_WORKERS` | Gunicorn processes in Compose, one database connection each |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | SMTP settings for booking and password-reset email |
| `VPS_TEST_SQLITE` | `1` runs the tests on SQLite instead of PostgreSQL |

</details>

<details>
<summary><b>No-show expiry on a server without Compose</b></summary>

Run the command every minute with cron, using the app's Python environment and exported settings:

```cron
* * * * * cd /app && python manage.py expire_no_shows
```

Repeated runs never charge the same booking twice.

</details>

<details>
<summary><b>Running the forecast service without Docker</b></summary>

```sh
python -m venv .venv-forecast
.venv-forecast/bin/pip install -r forecast/requirements-dev.txt
FORECAST_DB_URL=postgresql://forecast_ro:PASSWORD@localhost:5432/vps \
  .venv-forecast/bin/python -m forecast.train.train --model-dir models
FORECAST_MODEL_DIR=models .venv-forecast/bin/uvicorn forecast.app.main:app --port 8001
```

Then start Django with `FORECAST_URL=http://localhost:8001`. Until there are 4 weeks of history the trainer uses simulated arrivals, and the search page labels the result "Estimate".

</details>

## Testing

```sh
pytest                                                    # app tests on PostgreSQL
VPS_TEST_SQLITE=1 pytest                                  # or on SQLite
pytest --cov --cov-branch --cov-report=xml && python scripts/check_coverage.py coverage.xml
(cd forecast && ../.venv-forecast/bin/pytest)             # forecast service
pytest -c tests/system/pytest.ini                         # browser tests, against a running server
```

The browser tests use Playwright, and the load tests (`tests/system/locust_*.py`) use Locust. Install both separately; they are not in the requirements files. The system tests read `VPS_BASE_URL` (default `http://127.0.0.1:8100`), `VPS_HTTP_PROD_URL`, `VPS_TLS_URL` and `VPS_SERVER_LOGS`.

### Part 3 results

| Check | Result |
|---|---|
| App test suite | **771 passed**, 0 failed |
| Line / branch coverage | **95.94% / 91.01%** (CI gate: 70% / 60%) |
| Test Plan cases | **49 of 51 pass**, none fail; 2 not run (timed user trial, month-long uptime) |
| Forecast and browser tests | 16 and 17 passed |
| Load | 200 concurrent sessions with 0 failures; booking, check-in and check-out p95 of 120 ms or less at 50 users |
| Accessibility | 0 WCAG 2.1 AA violations (axe-core) on 15 pages |

Full reports: [unit tests](docs/part-3/unit-test-report.md) · [line coverage](docs/part-3/code-coverage-report.md) · [branch coverage](docs/part-3/branch-coverage-report.md) · [system validation](docs/part-3/system-validation-report.md) · [code review](docs/part-3/code-review.md) · [second review](docs/part-3/code-review-2.md) · [raw evidence](docs/part-3/evidence/)

### Continuous integration

Every pull request runs ruff, the forecast tests, the full suite on PostgreSQL 16 with the coverage gate, `pip-audit` on both requirements files, and a Gitleaks scan of the whole history.

## Project structure

```text
.
├── vps/                  Django project
│   ├── accounts/         users, roles, sign-in, staff and permits
│   ├── allocation/       slot eligibility and slot choice
│   ├── reservations/     search, booking, cancellation, no-show expiry
│   ├── gate/             check-in, check-out, walk-ins, payments, receipts
│   ├── billing/          charges, payments and waivers
│   ├── lots/             lots, slots, tariffs, blocking, live occupancy
│   ├── vehicles/         driver vehicles
│   ├── reports/          revenue, occupancy and audit log pages
│   ├── audit/            append-only audit log
│   └── notifications/    booking emails
├── forecast/             FastAPI forecast service and training job
├── templates/            Django templates
├── tests/                app tests; tests/system/ has browser and load tests
├── docker/postgres/init/ database initialisation scripts
├── scripts/              coverage gate
├── docs/                 Part 1 and Part 3 documents, README images
└── compose.yaml
```

## Documentation

| Document | Link |
|---|---|
| Software Requirements Specification | [`docs/part-1/VPS_SRS.docx`](docs/part-1/VPS_SRS.docx) |
| Software Test Plan | [`docs/part-1/VPS_Test_Plan.docx`](docs/part-1/VPS_Test_Plan.docx) |
| Software Architecture and Design | [`docs/part-1/VPS_SAD.docx`](docs/part-1/VPS_SAD.docx) |
| UML diagrams (PlantUML and PNG) | [`docs/part-1/diagrams/`](docs/part-1/diagrams/) |
| Part 3 test reports and evidence | [`docs/part-3/`](docs/part-3/) |
| Sprint 1 demo video | [`videos/VPS-Sprint-1-Demo.mp4`](videos/VPS-Sprint-1-Demo.mp4) |

## Team

Team 10, Section C · Software Engineering (UE24CS341A), Semester 5 · Department of Computer Science and Engineering, PES University

| Name | SRN | GitHub |
|---|---|---|
|D Harikrishnan  | PES1UG24CS136 | [@dhkrish06](https://github.com/dhkrish06) |
| Dhruv Purushotham Raju | PES1UG24CS154 | [@dhruvpurushotham1718-ui](https://github.com/dhruvpurushotham1718-ui) |
| A Gitanjali | PES1UG24CS170 | [@git17616](https://github.com/git17616) |
| Vivian Sobers E | PES1UG24CS901 | [@VivianSobers](https://github.com/VivianSobers) |
