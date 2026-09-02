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

The demo login is `demo-admin` / `pulse-demo`. The seed command prints the public feedback URL. Open `http://127.0.0.1:8000/admin/` to manage projects and cycles.

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
