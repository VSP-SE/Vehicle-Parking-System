# Vehicle Parking System

A web application for managing parking slots and tracking vehicles. It is the Level-3 mini-project for Software Engineering (UE24CS341A), Semester 5, Department of Computer Science and Engineering, PES University.

## Team


Team 10, Section C.

| Name | SRN | GitHub |
|---|---|---|
|D Harikrishnan  | PES1UG24CS136 | [@dhkrish06](https://github.com/dhkrish06) |
| Dhruv Purushotham Raju | PES1UG24CS154 | [@dhruvpurushotham1718-ui](https://github.com/dhruvpurushotham1718-ui) |
| A Gitanjali | PES1UG24CS170 | [@git17616](https://github.com/git17616) |
| Vivian Sobers E | PES1UG24CS901 | [@VivianSobers](https://github.com/VivianSobers) |

## Planned stack

- Backend: Python, Django and Django REST Framework
- Model service: FastAPI
- Database: PostgreSQL
- Frontend: server-rendered Django templates

## Tooling

| Purpose | Tool |
|---|---|
| Version control | Git and GitHub |
| Agile planning and bug tracking | GitHub Projects |
| CI | GitHub Actions: ruff, PostgreSQL tests, coverage gates and security scans |
| Testing | pytest with branch coverage |

## Deliverables

Part 1 deliverables are in [`docs/part-1/`](docs/part-1/) as Word files:

| Deliverable | File |
|---|---|
| Software Requirements Specification | [`VPS_SRS.docx`](docs/part-1/VPS_SRS.docx) |
| Software Test Plan, with test cases | [`VPS_Test_Plan.docx`](docs/part-1/VPS_Test_Plan.docx) |
| Software Architecture and Design Specification | [`VPS_SAD.docx`](docs/part-1/VPS_SAD.docx) |

The UML diagrams are in [`docs/part-1/diagrams/`](docs/part-1/diagrams/) as PlantUML sources with rendered PNGs.

## Running locally

Use Python 3.12 or newer and a local PostgreSQL 16 database. Create the database
and user, then set their credentials in `.env` along with a generated Django
secret key. Django reads exported environment variables; it does not load `.env`
automatically. The example file uses shell-compatible values.

```sh
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Edit .env with your local values, then export them into the shell.
set -a
source .env
set +a
python manage.py migrate
python manage.py runserver
pytest
```

The database user needs permission to create the test database for PostgreSQL
tests. To run tests without PostgreSQL, use `VPS_TEST_SQLITE=1 pytest`.

## Status

Sprint 1 is under way. The Django project skeleton is in place. CI runs ruff, the test suite on PostgreSQL 16 with a 70% line and 60% branch coverage gate, pip-audit and a Gitleaks secret scan on every pull request.
