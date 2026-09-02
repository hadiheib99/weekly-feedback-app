from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedbackCycle, Project, Response


class FeedbackFlowTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Mobile app", description="Core journey redesign")
        self.cycle = FeedbackCycle.objects.create(
            project=self.project,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=1),
        )
        self.url = reverse("feedback_form", args=[self.cycle.token])

    def test_public_feedback_submission(self):
        response = self.client.post(self.url, {"score": 4, "comment": "Going well"}, REMOTE_ADDR="10.0.0.1")
        self.assertRedirects(response, reverse("feedback_thanks", args=[self.cycle.token]))
        saved = Response.objects.get()
        self.assertEqual(saved.score, 4)
        self.assertNotEqual(saved.network_hash, "10.0.0.1")
        self.assertTrue(response.cookies["pulse_device"]["httponly"])

    def test_duplicate_network_gets_generic_error(self):
        self.client.post(self.url, {"score": 4}, REMOTE_ADDR="10.0.0.1")
        other_browser = self.client_class()
        response = other_browser.post(self.url, {"score": 5}, REMOTE_ADDR="10.0.0.1")
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Unable to submit", status_code=409)
        self.assertEqual(Response.objects.count(), 1)

    def test_closed_cycle_rejects_feedback(self):
        self.cycle.closes_at = timezone.now() - timedelta(minutes=1)
        self.cycle.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class DashboardAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.lead = User.objects.create_user("lead", password="test-password")
        self.other = User.objects.create_user("other", password="test-password")
        self.project = Project.objects.create(name="Assigned")
        self.project.leads.add(self.lead)
        self.cycle = FeedbackCycle.objects.create(
            project=self.project,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=1),
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_lead_sees_assigned_project(self):
        self.client.login(username="lead", password="test-password")
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Assigned")

    def test_other_user_cannot_open_project_dashboard(self):
        self.client.login(username="other", password="test-password")
        response = self.client.get(reverse("project_dashboard", args=[self.project.id]))
        self.assertEqual(response.status_code, 404)

# Create your tests here.
