from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedbackCycle, Project, Response


class CycleAvailabilityTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.project = Project.objects.create(
            name="Visible project",
            description="Confidential project description",
        )

    def make_cycle(self, opens_at=None, closes_at=None, project=None):
        return FeedbackCycle.objects.create(
            project=project or self.project,
            opens_at=opens_at or self.now - timedelta(hours=1),
            closes_at=closes_at or self.now + timedelta(hours=1),
        )

    def assert_no_form_or_response(self, response):
        self.assertNotContains(response, "Submit anonymous feedback", status_code=403)
        self.assertEqual(Response.objects.count(), 0)

    def test_open_cycle_get_displays_form_and_post_creates_one_response(self):
        cycle = self.make_cycle()
        url = reverse("feedback_form", args=[cycle.token])

        self.assertContains(self.client.get(url), "Submit anonymous feedback")
        response = self.client.post(url, {"score": "4", "comment": "On track"}, REMOTE_ADDR="192.0.2.1")

        self.assertRedirects(response, reverse("feedback_thanks", args=[cycle.token]))
        self.assertEqual(Response.objects.filter(cycle=cycle).count(), 1)

    def test_opening_and_closing_boundaries_accept_get_and_post(self):
        for boundary in ("opens_at", "closes_at"):
            with self.subTest(boundary=boundary):
                cycle = self.make_cycle()
                instant = getattr(cycle, boundary)
                url = reverse("feedback_form", args=[cycle.token])
                with patch("feedback.views.timezone.now", return_value=instant):
                    self.assertContains(self.client.get(url), "Submit anonymous feedback")
                    response = self.client.post(
                        url,
                        {"score": "3", "comment": "Boundary"},
                        REMOTE_ADDR=f"192.0.2.{Response.objects.count() + 10}",
                    )
                self.assertRedirects(response, reverse("feedback_thanks", args=[cycle.token]))
                self.assertEqual(Response.objects.filter(cycle=cycle).count(), 1)
                self.client.cookies.clear()

    def test_future_cycle_get_and_post_are_unavailable(self):
        cycle = self.make_cycle(self.now + timedelta(hours=1), self.now + timedelta(hours=2))
        url = reverse("feedback_form", args=[cycle.token])

        self.assertContains(self.client.get(url), "not currently open", status_code=403)
        response = self.client.post(url, {"score": "5"})

        self.assertContains(response, "not currently open", status_code=403)
        self.assert_no_form_or_response(response)

    def test_expired_cycle_get_and_post_are_closed(self):
        cycle = self.make_cycle(self.now - timedelta(hours=2), self.now - timedelta(hours=1))
        url = reverse("feedback_form", args=[cycle.token])

        self.assertContains(self.client.get(url), "check-in is closed", status_code=403)
        response = self.client.post(url, {"score": "5"})

        self.assertContains(response, "check-in is closed", status_code=403)
        self.assert_no_form_or_response(response)

    def test_inactive_project_get_and_post_are_generic_and_non_leaking(self):
        self.project.is_active = False
        self.project.save(update_fields=["is_active"])
        cycle = self.make_cycle()
        url = reverse("feedback_form", args=[cycle.token])

        for response in (self.client.get(url), self.client.post(url, {"score": "5"})):
            self.assertContains(response, "check-in is unavailable", status_code=403)
            self.assertNotContains(response, self.project.name, status_code=403)
            self.assertNotContains(response, self.project.description, status_code=403)
            self.assertNotContains(response, str(cycle.opens_at), status_code=403)
            self.assertNotContains(response, str(cycle.closes_at), status_code=403)
            self.assert_no_form_or_response(response)

    def test_unknown_and_malformed_tokens_return_404_without_saving(self):
        for token in ("does-not-exist", "malformed!token"):
            with self.subTest(token=token):
                url = reverse("feedback_form", args=[token])
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, {"score": "4"}).status_code, 404)
        self.assertEqual(Response.objects.count(), 0)

    def test_post_rechecks_cycle_and_project_availability(self):
        for change in ("closed", "inactive"):
            with self.subTest(change=change):
                project = Project.objects.create(name=f"Project {change}")
                cycle = self.make_cycle(project=project)
                url = reverse("feedback_form", args=[cycle.token])
                self.assertEqual(self.client.get(url).status_code, 200)
                if change == "closed":
                    cycle.closes_at = self.now - timedelta(seconds=1)
                    cycle.save(update_fields=["closes_at"])
                else:
                    project.is_active = False
                    project.save(update_fields=["is_active"])

                response = self.client.post(url, {"score": "4"}, REMOTE_ADDR="192.0.2.30")

                self.assertEqual(response.status_code, 403)
                self.assertEqual(Response.objects.filter(cycle=cycle).count(), 0)

    def test_home_selects_latest_opening_then_lowest_id(self):
        older = self.make_cycle(self.now - timedelta(hours=2), self.now + timedelta(hours=1))
        tied_first = self.make_cycle(self.now - timedelta(hours=1), self.now + timedelta(hours=1))
        self.make_cycle(self.now - timedelta(hours=1), self.now + timedelta(hours=2))

        response = self.client.get(reverse("home"))

        self.assertRedirects(response, reverse("feedback_form", args=[tied_first.token]), fetch_redirect_response=False)
        self.assertNotEqual(older.id, tied_first.id)

    def test_home_empty_state_for_every_no_available_cycle_case(self):
        cases = (
            lambda: None,
            lambda: self.make_cycle(self.now + timedelta(hours=1), self.now + timedelta(hours=2)),
            lambda: self.make_cycle(self.now - timedelta(hours=2), self.now - timedelta(hours=1)),
            self._make_inactive_cycle,
        )
        for index, setup in enumerate(cases):
            with self.subTest(case=index):
                FeedbackCycle.objects.all().delete()
                setup()
                response = self.client.get(reverse("home"))
                self.assertContains(response, "No active feedback cycle is available")
                self.assertNotContains(response, "Submit anonymous feedback")

    def _make_inactive_cycle(self):
        project = Project.objects.create(name="Inactive", is_active=False)
        return self.make_cycle(project=project)
