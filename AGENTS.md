# Project Instructions

## Commands

- `python3 -m venv /tmp/pulse-venv` — create a virtual environment outside the repository.
- `/tmp/pulse-venv/bin/pip install -r requirements.txt` — install dependencies.
- `/tmp/pulse-venv/bin/python manage.py migrate` — apply database migrations.
- `/tmp/pulse-venv/bin/python manage.py test` — run the complete test suite.
- `/tmp/pulse-venv/bin/python manage.py test feedback.tests` — run the feedback app tests.
- `/tmp/pulse-venv/bin/python manage.py runserver` — start the local development server.

## Rules

- GitHub issues are the canonical backlog; process one issue at a time.
- Dependencies are declared in `requirements.txt`. Do not add a dependency without asking.
- Never commit credentials, local databases, virtual environments, cache files, or production secrets.
- Read an issue's acceptance criteria before implementation and again before handoff.
- Keep role responsibilities separate as described in `_docs/process.md`.

## Documents

- `_docs/process.md` — workflow, roles, lifecycle, and issue-closing rules.
- `_docs/task-template.md` — required structure for groomed issues.
- `_docs/team/pm.md` — Product Manager responsibilities.
- `_docs/team/software-engineer.md` — Software Engineer responsibilities.
- `_docs/team/qa-engineer.md` — QA Engineer responsibilities.
- `_docs/issues/` — reviewable local copies of groomed issue specifications.
