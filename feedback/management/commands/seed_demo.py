from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from feedback.models import FeedbackCycle, Project


class Command(BaseCommand):
    help = "Create a local demo admin, project, and open weekly cycle"

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(username="demo-admin", defaults={"is_staff": True, "is_superuser": True})
        if created:
            user.set_password("pulse-demo")
            user.save()

        project, _ = Project.objects.get_or_create(
            name="Mobile app redesign",
            defaults={"description": "Refreshing the core customer journey and visual system."},
        )
        project.leads.add(user)
        now = timezone.now()
        cycle = project.cycles.filter(opens_at__lte=now, closes_at__gte=now).first()
        if not cycle:
            cycle = FeedbackCycle.objects.create(project=project, opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=6))

        self.stdout.write(self.style.SUCCESS("Demo data is ready"))
        self.stdout.write("Admin login: demo-admin / pulse-demo")
        self.stdout.write(f"Public form: /feedback/{cycle.token}/")
