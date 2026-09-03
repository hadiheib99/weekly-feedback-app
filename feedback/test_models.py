from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import FeedbackCycle, Project, Response


class ProjectModelTests(TestCase):
    def test_project_defaults_and_string_label(self):
        project = Project.objects.create(name="Mobile app")

        self.assertEqual(str(project), "Mobile app")
        self.assertEqual(Project._meta.get_field("name").max_length, 160)
        self.assertEqual(project.description, "")
        self.assertTrue(project.is_active)
        self.assertIsNotNone(project.created_at)

    def test_project_requires_a_name(self):
        with self.assertRaises(ValidationError):
            Project(name="").full_clean()

    def test_projects_and_leads_have_many_to_many_relationship(self):
        user_model = get_user_model()
        first_lead = user_model.objects.create_user("first-lead")
        second_lead = user_model.objects.create_user("second-lead")
        first_project = Project.objects.create(name="First")
        second_project = Project.objects.create(name="Second")

        self.assertEqual(first_project.leads.count(), 0)
        first_project.leads.add(first_lead, second_lead)
        second_project.leads.add(first_lead)

        self.assertCountEqual(first_project.leads.all(), [first_lead, second_lead])
        self.assertCountEqual(first_lead.led_projects.all(), [first_project, second_project])

    def test_deleting_a_lead_preserves_project_and_feedback(self):
        user_model = get_user_model()
        lead = user_model.objects.create_user("lead")
        project = Project.objects.create(name="Preserved")
        project.leads.add(lead)
        cycle = FeedbackCycle.objects.create(
            project=project,
            opens_at=timezone.now(),
            closes_at=timezone.now() + timedelta(days=7),
        )
        response = Response.objects.create(
            cycle=cycle,
            score=4,
            network_hash="n" * 64,
            device_hash="d" * 64,
        )

        lead.delete()

        self.assertTrue(Project.objects.filter(pk=project.pk).exists())
        self.assertTrue(FeedbackCycle.objects.filter(pk=cycle.pk).exists())
        self.assertTrue(Response.objects.filter(pk=response.pk).exists())

    def test_deleting_project_cascades_to_cycles_and_responses(self):
        project = Project.objects.create(name="Deleted")
        cycle = FeedbackCycle.objects.create(
            project=project,
            opens_at=timezone.now(),
            closes_at=timezone.now() + timedelta(days=7),
        )
        Response.objects.create(
            cycle=cycle,
            score=3,
            network_hash="n" * 64,
            device_hash="d" * 64,
        )

        project.delete()

        self.assertEqual(FeedbackCycle.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 0)


class FeedbackCycleModelTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Website")
        self.now = timezone.now()

    def cycle(self, opens_at=None, closes_at=None):
        return FeedbackCycle(
            project=self.project,
            opens_at=opens_at or self.now,
            closes_at=closes_at or self.now + timedelta(days=7),
        )

    def test_cycle_has_unique_automatic_token_and_readable_label(self):
        first = self.cycle()
        second = self.cycle(
            opens_at=self.now + timedelta(days=8),
            closes_at=self.now + timedelta(days=15),
        )
        first.full_clean()
        first.save()
        second.full_clean()
        second.save()

        token_field = FeedbackCycle._meta.get_field("token")
        self.assertNotEqual(first.token, second.token)
        self.assertTrue(token_field.unique)
        self.assertFalse(token_field.editable)
        self.assertIn(self.project.name, str(first))
        self.assertIn(self.now.strftime("%Y-%m-%d"), str(first))

    def test_cycle_rejects_closing_at_opening_time(self):
        cycle = self.cycle(closes_at=self.now)

        with self.assertRaisesMessage(ValidationError, "Closing time must be after opening time"):
            cycle.full_clean()

    def test_cycle_rejects_closing_before_opening_time(self):
        cycle = self.cycle(closes_at=self.now - timedelta(seconds=1))

        with self.assertRaisesMessage(ValidationError, "Closing time must be after opening time"):
            cycle.full_clean()

    def test_database_rejects_invalid_cycle_when_validation_is_bypassed(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            FeedbackCycle.objects.create(
                project=self.project,
                opens_at=self.now,
                closes_at=self.now,
            )

    def test_cycle_is_open_at_exact_opening_time(self):
        cycle = self.cycle()

        with patch("feedback.models.timezone.now", return_value=cycle.opens_at):
            self.assertTrue(cycle.is_open)

    def test_cycle_is_open_at_exact_closing_time(self):
        cycle = self.cycle()

        with patch("feedback.models.timezone.now", return_value=cycle.closes_at):
            self.assertTrue(cycle.is_open)

    def test_cycle_is_closed_before_opening(self):
        cycle = self.cycle()

        with patch("feedback.models.timezone.now", return_value=cycle.opens_at - timedelta(microseconds=1)):
            self.assertFalse(cycle.is_open)

    def test_cycle_is_closed_after_closing(self):
        cycle = self.cycle()

        with patch("feedback.models.timezone.now", return_value=cycle.closes_at + timedelta(microseconds=1)):
            self.assertFalse(cycle.is_open)

    def test_cycles_are_ordered_by_newest_opening_first(self):
        older = self.cycle()
        older.save()
        newer = self.cycle(
            opens_at=self.now + timedelta(days=8),
            closes_at=self.now + timedelta(days=15),
        )
        newer.save()

        self.assertEqual(list(FeedbackCycle.objects.all()), [newer, older])


class ResponseModelTests(TestCase):
    def setUp(self):
        project = Project.objects.create(name="API")
        self.cycle = FeedbackCycle.objects.create(
            project=project,
            opens_at=timezone.now(),
            closes_at=timezone.now() + timedelta(days=7),
        )

    def response(self, score=3, **overrides):
        values = {
            "cycle": self.cycle,
            "score": score,
            "network_hash": "n" * 64,
            "device_hash": "d" * 64,
        }
        values.update(overrides)
        return Response(**values)

    def test_response_accepts_boundary_scores_and_blank_comment(self):
        for score in (1, 5):
            response = self.response(
                score=score,
                network_hash=str(score) * 64,
                device_hash=str(score + 1) * 64,
            )
            response.full_clean()
            response.save()
            self.assertEqual(response.comment, "")
            self.assertIsNotNone(response.created_at)

    def test_response_rejects_invalid_scores(self):
        for score in (0, 6, -1, "not-an-integer", None):
            with self.subTest(score=score), self.assertRaises(ValidationError):
                self.response(score=score).full_clean()

    def test_response_has_no_direct_identity_field(self):
        field_names = {field.name for field in Response._meta.get_fields()}

        self.assertTrue({"cycle", "score", "comment", "created_at"} <= field_names)
        self.assertTrue({"user", "email", "name"}.isdisjoint(field_names))

    def test_responses_are_ordered_by_newest_creation_first(self):
        older = self.response()
        older.save()
        newer = self.response(network_hash="x" * 64, device_hash="y" * 64)
        newer.save()
        Response.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=1))

        self.assertEqual(list(Response.objects.all()), [newer, older])
