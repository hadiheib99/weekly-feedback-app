from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .management.commands.seed_demo import (
    ADMIN_PASSWORD, ADMIN_USERNAME, CLOSED_CYCLE_TOKEN, LEAD_PASSWORD, LEAD_USERNAME, OPEN_CYCLE_TOKEN, PROJECTS,
)
from .models import FeedbackCycle, Project, Response


@override_settings(DEBUG=True)
class SeedDemoTests(TestCase):
    def run_seed(self):
        output = StringIO()
        call_command("seed_demo", stdout=output)
        return output.getvalue()

    def test_clean_seed_creates_complete_representative_data(self):
        output = self.run_seed()
        User = get_user_model()
        self.assertEqual(User.objects.filter(username__in=[ADMIN_USERNAME, LEAD_USERNAME]).count(), 2)
        admin_user, lead = User.objects.get(username=ADMIN_USERNAME), User.objects.get(username=LEAD_USERNAME)
        self.assertTrue(admin_user.is_staff and admin_user.is_superuser)
        self.assertFalse(lead.is_staff or lead.is_superuser)
        projects = Project.objects.filter(name__in=[item[0] for item in PROJECTS])
        self.assertEqual(projects.count(), 2)
        self.assertTrue(all(project.is_active for project in projects))
        self.assertEqual(projects.filter(leads=lead).count(), 1)
        now = timezone.now()
        open_cycle = FeedbackCycle.objects.get(token=OPEN_CYCLE_TOKEN)
        closed_cycle = FeedbackCycle.objects.get(token=CLOSED_CYCLE_TOKEN)
        self.assertEqual(open_cycle.project, closed_cycle.project)
        self.assertTrue(open_cycle.opens_at <= now <= open_cycle.closes_at)
        self.assertLess(closed_cycle.closes_at, now)
        for cycle in (open_cycle, closed_cycle):
            self.assertTrue(timezone.is_aware(cycle.opens_at) and timezone.is_aware(cycle.closes_at))
            self.assertLess(cycle.opens_at, cycle.closes_at)
        responses = Response.objects.filter(cycle__token__in=[OPEN_CYCLE_TOKEN, CLOSED_CYCLE_TOKEN])
        self.assertTrue({1, 3, 5}.issubset(set(responses.values_list("score", flat=True))))
        self.assertTrue(responses.filter(comment="").exists() and responses.exclude(comment="").exists())
        for response in responses:
            self.assertRegex(response.network_hash, r"^[0-9a-f]{64}$")
            self.assertRegex(response.device_hash, r"^[0-9a-f]{64}$")
            self.assertNotEqual(response.network_hash, response.device_hash)
        self.assertIn("Demo data is ready", output)

    def test_credentials_roles_dashboards_admin_and_public_link_work(self):
        self.run_seed()
        for username, password in ((ADMIN_USERNAME, ADMIN_PASSWORD), (LEAD_USERNAME, LEAD_PASSWORD)):
            self.client.logout()
            login = self.client.post(reverse("login"), {"username": username, "password": password})
            self.assertRedirects(login, reverse("dashboard"), fetch_redirect_response=False)
            dashboard = self.client.get(reverse("dashboard"))
            self.assertEqual(dashboard.status_code, 200)
            expected_rows = 2 if username == ADMIN_USERNAME else 1
            self.assertContains(dashboard, 'class="project-row"', count=expected_rows)
        self.client.logout()
        self.assertTrue(self.client.login(username=ADMIN_USERNAME, password=ADMIN_PASSWORD))
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.client.logout()
        self.assertTrue(self.client.login(username=LEAD_USERNAME, password=LEAD_PASSWORD))
        self.assertNotEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.client.logout()
        cycle = FeedbackCycle.objects.get(token=OPEN_CYCLE_TOKEN)
        self.assertContains(self.client.get(reverse("feedback_form", args=[cycle.token])), "Submit anonymous feedback")

    def test_output_contains_credentials_urls_and_current_public_identity(self):
        output = self.run_seed()
        for text in (ADMIN_USERNAME, ADMIN_PASSWORD, LEAD_USERNAME, LEAD_PASSWORD, "/dashboard/", "/admin/", f"/feedback/{OPEN_CYCLE_TOKEN}/"):
            self.assertIn(text, output)

    def test_second_run_is_idempotent_and_keeps_record_identities(self):
        first_output = self.run_seed()
        def identities():
            return (
                list(get_user_model().objects.filter(username__in=[ADMIN_USERNAME, LEAD_USERNAME]).values_list("pk", flat=True)),
                list(Project.objects.filter(name__in=[item[0] for item in PROJECTS]).values_list("pk", flat=True)),
                list(FeedbackCycle.objects.filter(token__in=[OPEN_CYCLE_TOKEN, CLOSED_CYCLE_TOKEN]).values_list("pk", flat=True)),
                list(Response.objects.filter(cycle__token__in=[OPEN_CYCLE_TOKEN, CLOSED_CYCLE_TOKEN]).values_list("pk", flat=True)),
            )
        first = identities()
        second_output = self.run_seed()
        self.assertEqual(first, identities())
        self.assertEqual(first_output.splitlines()[-3:], second_output.splitlines()[-3:])

    def test_drift_is_reconciled_without_touching_unrelated_records(self):
        self.run_seed()
        User = get_user_model()
        admin_user, lead = User.objects.get(username=ADMIN_USERNAME), User.objects.get(username=LEAD_USERNAME)
        admin_user.is_staff = admin_user.is_superuser = False
        admin_user.set_password("drifted")
        admin_user.save()
        primary = Project.objects.get(name=PROJECTS[0][0])
        primary.is_active = False
        primary.save(update_fields=["is_active"])
        primary.leads.clear()
        unrelated_user = User.objects.create_user("unrelated", password="unchanged-password")
        unrelated = Project.objects.create(name="Unrelated project", description="Do not change", is_active=False)
        unrelated.leads.add(unrelated_user)
        self.run_seed()
        admin_user.refresh_from_db()
        primary.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertTrue(admin_user.is_staff and admin_user.is_superuser and admin_user.check_password(ADMIN_PASSWORD))
        self.assertTrue(primary.is_active)
        self.assertQuerySetEqual(primary.leads.all(), [lead])
        self.assertEqual((unrelated.description, unrelated.is_active), ("Do not change", False))
        self.assertQuerySetEqual(unrelated.leads.all(), [unrelated_user])

    def test_failure_rolls_back_every_partial_demo_mutation(self):
        with patch("feedback.management.commands.seed_demo.Command._seed_responses", side_effect=RuntimeError("failure")), self.assertRaises(RuntimeError):
            self.run_seed()
        self.assertFalse(get_user_model().objects.filter(username__in=[ADMIN_USERNAME, LEAD_USERNAME]).exists())
        self.assertFalse(Project.objects.filter(name__in=[item[0] for item in PROJECTS]).exists())
        self.assertFalse(FeedbackCycle.objects.filter(token__in=[OPEN_CYCLE_TOKEN, CLOSED_CYCLE_TOKEN]).exists())

    @override_settings(DEBUG=False)
    def test_debug_false_refuses_with_safety_message_and_no_changes(self):
        unrelated = Project.objects.create(name="Existing untouched")
        with self.assertRaisesMessage(CommandError, "local demonstration only"):
            self.run_seed()
        self.assertEqual(list(Project.objects.all()), [unrelated])
        self.assertFalse(get_user_model().objects.filter(username__in=[ADMIN_USERNAME, LEAD_USERNAME]).exists())
