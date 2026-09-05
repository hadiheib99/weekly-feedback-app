# Pulse

A Django MVP for anonymous weekly project feedback.

## Run locally

Create the virtual environment on your internal drive (macOS external drives can create `._*.pth` metadata that breaks Python environments), then run:

```bash
python3 -m venv /tmp/pulse-venv
/tmp/pulse-venv/bin/pip install -r requirements.txt
/tmp/pulse-venv/bin/python manage.py migrate
/tmp/pulse-venv/bin/python manage.py seed_demo
/tmp/pulse-venv/bin/python manage.py runserver
```

## Local demonstration data

`python manage.py seed_demo` is for local demonstration only and refuses to run when `DEBUG=False`. In the virtual environment used above, run:

```bash
/tmp/pulse-venv/bin/python manage.py seed_demo
```

The command reconciles the same demo records each time and prints the current public feedback link. These credentials are intentionally unsafe and must never be used in production:

- Administrator: `demo-admin` / `pulse-demo-admin`
- Project lead: `demo-lead` / `pulse-demo-lead`

After seeding, both users can sign in at `http://127.0.0.1:8000/accounts/login/`; the administrator can also enter `http://127.0.0.1:8000/admin/`.

## Product decisions represented

- Public weekly feedback link with a 1–5 health score and optional comment
- Anonymous responses and a concise privacy note
- Hashed IP and device-cookie duplicate protection, with no editing
- Lead-only project results, trends, distribution, comments, and exports
- Admin portfolio comparison and project management entry point
- Two signed-in roles: admin and project lead
- English-first responsive web experience

## Current boundaries

The MVP uses SQLite and Django's username/password authentication. Google/Microsoft/passwordless login, automatic weekly-cycle scheduling, QR generation, and CSV/PDF exports are the next production milestone.
# weekly-feedback-app
