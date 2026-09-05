import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from feedback.models import FeedbackCycle, Project, Response

ADMIN_USERNAME = "demo-admin"
ADMIN_PASSWORD = "pulse-demo-admin"
LEAD_USERNAME = "demo-lead"
LEAD_PASSWORD = "pulse-demo-lead"
PROJECTS = (
    ("Demo Mobile Redesign", "A customer journey redesign used for local demonstration."),
    ("Demo Platform Migration", "A platform migration visible to demo administrators."),
)
OPEN_CYCLE_TOKEN = "demo-open-cycle-v1"
CLOSED_CYCLE_TOKEN = "demo-closed-cycle-v1"


def demo_hash(raw_identifier):
    return hashlib.sha256(f"{settings.FEEDBACK_HASH_SALT}:{raw_identifier}".encode()).hexdigest()


class Command(BaseCommand):
    help = "Create or reconcile deterministic local demonstration data"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo data is for local demonstration only; refusing to run while DEBUG=False.")
        with transaction.atomic():
            admin_user, lead_user = self._seed_users()
            primary, secondary = self._seed_projects(lead_user)
            open_cycle, closed_cycle = self._seed_cycles(primary)
            self._seed_responses(open_cycle, closed_cycle)
        self.stdout.write(self.style.SUCCESS("Demo data is ready"))
        self.stdout.write("Unsafe local-only credentials:")
        self.stdout.write(f"Administrator: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
        self.stdout.write(f"Project lead: {LEAD_USERNAME} / {LEAD_PASSWORD}")
        self.stdout.write("Dashboard: /dashboard/")
        self.stdout.write("Django admin: /admin/")
        self.stdout.write(f"Public feedback: /feedback/{open_cycle.token}/")
        self.stdout.write(f"Demo projects: {primary.name}; {secondary.name}")

    def _seed_users(self):
        User = get_user_model()
        admin_user, _ = User.objects.get_or_create(username=ADMIN_USERNAME)
        admin_user.is_staff = admin_user.is_superuser = admin_user.is_active = True
        admin_user.set_password(ADMIN_PASSWORD)
        admin_user.save()
        lead_user, _ = User.objects.get_or_create(username=LEAD_USERNAME)
        lead_user.is_staff = lead_user.is_superuser = False
        lead_user.is_active = True
        lead_user.set_password(LEAD_PASSWORD)
        lead_user.save()
        return admin_user, lead_user

    def _seed_projects(self, lead_user):
        projects = []
        for name, description in PROJECTS:
            project, _ = Project.objects.update_or_create(
                name=name, defaults={"description": description, "is_active": True}
            )
            projects.append(project)
        projects[0].leads.set([lead_user])
        projects[1].leads.clear()
        return projects

    def _seed_cycles(self, primary):
        now = timezone.now()
        open_cycle, _ = FeedbackCycle.objects.update_or_create(
            token=OPEN_CYCLE_TOKEN,
            defaults={"project": primary, "opens_at": now - timedelta(days=1), "closes_at": now + timedelta(days=6)},
        )
        closed_cycle, _ = FeedbackCycle.objects.update_or_create(
            token=CLOSED_CYCLE_TOKEN,
            defaults={"project": primary, "opens_at": now - timedelta(days=14), "closes_at": now - timedelta(days=7)},
        )
        return open_cycle, closed_cycle

    def _seed_responses(self, open_cycle, closed_cycle):
        samples = (
            (open_cycle, 1, "A blocker needs attention.", "open-1"),
            (open_cycle, 3, "", "open-2"),
            (open_cycle, 5, "The latest milestone went very well.", "open-3"),
            (closed_cycle, 3, "Useful historical context.", "closed-1"),
        )
        for cycle, score, comment, identity in samples:
            Response.objects.update_or_create(
                cycle=cycle,
                network_hash=demo_hash(f"demo-network-{identity}"),
                defaults={"score": score, "comment": comment, "device_hash": demo_hash(f"demo-device-{identity}")},
            )
