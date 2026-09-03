from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedbackCycle, Project, Response


class PublicFeedbackSubmissionTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Mobile app",
            description="Core journey redesign",
        )
        self.cycle = FeedbackCycle.objects.create(
            project=self.project,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=1),
        )
        self.form_url = reverse("feedback_form", args=[self.cycle.token])
        self.thanks_url = reverse("feedback_thanks", args=[self.cycle.token])

    def test_signed_out_visitor_sees_complete_public_form(self):
        response = self.client.get(self.form_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.name)
        self.assertContains(response, "Weekly project check-in")
        self.assertContains(response, "How is the project feeling this week?")
        for score in range(1, 6):
            self.assertContains(response, f'value="{score}"')
        self.assertContains(response, "1 — Critical")
        self.assertContains(response, "5 — Excellent")
        self.assertContains(response, "Optional")
        self.assertContains(response, "Submit anonymous feedback")
        self.assertContains(response, "Your response is anonymous")
        self.assertContains(
            response,
            "project leads cannot see them",
        )

    def test_every_valid_score_creates_one_response_with_blank_comment(self):
        for score in range(1, 6):
            with self.subTest(score=score):
                self.client.cookies.clear()
                response = self.client.post(
                    self.form_url,
                    {"score": str(score), "comment": ""},
                    REMOTE_ADDR=f"192.0.2.{score}",
                )

                self.assertRedirects(response, self.thanks_url)
                saved = Response.objects.get(score=score)
                self.assertEqual(saved.cycle, self.cycle)
                self.assertEqual(saved.comment, "")
        self.assertEqual(Response.objects.count(), 5)

    def test_comment_is_preserved_on_success_and_confirmation_names_project(self):
        comment = "The release is progressing well."

        response = self.client.post(
            self.form_url,
            {"score": "4", "comment": comment},
            REMOTE_ADDR="192.0.2.20",
        )

        self.assertRedirects(response, self.thanks_url)
        saved = Response.objects.get()
        self.assertEqual(saved.comment, comment)
        confirmation = self.client.get(self.thanks_url)
        self.assertContains(confirmation, self.project.name)
        self.assertContains(confirmation, "anonymous feedback")
        self.assertContains(confirmation, "has been submitted")

    def test_missing_and_malformed_scores_show_same_error_without_saving(self):
        for score in (None, "0", "6", "2.5", "not-a-number"):
            with self.subTest(score=score):
                data = {"comment": "Please preserve this context."}
                if score is not None:
                    data["score"] = score

                response = self.client.post(
                    self.form_url,
                    data,
                    REMOTE_ADDR="192.0.2.30",
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Choose a score from 1 to 5.")
                self.assertContains(response, "Please preserve this context.")
                self.assertEqual(Response.objects.count(), 0)

    def test_server_owned_fields_cannot_be_overridden_by_form_input(self):
        other_project = Project.objects.create(name="Other project")
        other_cycle = FeedbackCycle.objects.create(
            project=other_project,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=1),
        )
        supplied_created_at = "2000-01-01T00:00:00Z"

        response = self.client.post(
            self.form_url,
            {
                "score": "3",
                "comment": "Server-owned fields stay protected.",
                "cycle": str(other_cycle.pk),
                "project": str(other_project.pk),
                "network_hash": "attacker-network-value",
                "device_hash": "attacker-device-value",
                "created_at": supplied_created_at,
            },
            REMOTE_ADDR="192.0.2.40",
        )

        self.assertRedirects(response, self.thanks_url)
        saved = Response.objects.get()
        self.assertEqual(saved.cycle, self.cycle)
        self.assertEqual(saved.cycle.project, self.project)
        self.assertNotEqual(saved.network_hash, "attacker-network-value")
        self.assertNotEqual(saved.device_hash, "attacker-device-value")
        self.assertNotEqual(saved.created_at.isoformat(), supplied_created_at)
