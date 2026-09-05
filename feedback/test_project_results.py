from datetime import timedelta
from html import escape

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from .models import FeedbackCycle, Project, Response


class ProjectResultsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("lead")
        self.project = Project.objects.create(name="Complete project name")
        self.project.leads.add(self.user)
        self.client.force_login(self.user)
        self.url = reverse("project_dashboard", args=[self.project.id])
        self.suffix = 1

    def cycle(self, opens_at, project=None):
        return FeedbackCycle.objects.create(
            project=project or self.project,
            opens_at=opens_at,
            closes_at=opens_at + timedelta(hours=2),
        )

    def add_response(self, cycle, score, comment=""):
        suffix = self.suffix
        self.suffix += 1
        return Response.objects.create(
            cycle=cycle,
            score=score,
            comment=comment,
            network_hash=f"{suffix:064x}",
            device_hash=f"{suffix + 10000:064x}",
        )

    def test_page_names_project_and_is_titled_weekly_health(self):
        self.cycle(timezone.now())
        response = self.client.get(self.url)
        self.assertContains(response, self.project.name)
        self.assertContains(response, "Weekly health")

    def test_latest_cycle_uses_opening_descending_then_id_descending(self):
        now = timezone.now()
        older = self.cycle(now - timedelta(days=1))
        tied_first = self.cycle(now + timedelta(days=1))
        tied_second = self.cycle(now + timedelta(days=1))
        self.add_response(older, 1, "older comment")
        self.add_response(tied_first, 2, "first tie comment")
        self.add_response(tied_second, 5, "selected tie comment")
        response = self.client.get(self.url)
        self.assertContains(response, "selected tie comment")
        self.assertContains(response, "5.0")
        self.assertNotContains(response, "older comment")
        self.assertNotContains(response, "first tie comment")

    def test_latest_selection_ignores_closed_open_or_future_state(self):
        now = timezone.now()
        for index, opens_at in enumerate((now - timedelta(days=3), now - timedelta(minutes=30), now + timedelta(days=3))):
            with self.subTest(index=index):
                FeedbackCycle.objects.all().delete()
                cycle = self.cycle(opens_at)
                self.add_response(cycle, index + 1, f"state-{index}")
                self.assertContains(self.client.get(self.url), f"state-{index}")

    def test_selected_cycle_dates_use_local_timezone_with_day_month_and_year(self):
        cycle = self.cycle(timezone.now() + timedelta(days=2))
        response = self.client.get(self.url)
        self.assertContains(response, date_format(timezone.localtime(cycle.opens_at), "M j, Y, g:i A"))
        self.assertContains(response, date_format(timezone.localtime(cycle.closes_at), "M j, Y, g:i A"))

    def test_metrics_and_distribution_use_only_selected_cycle(self):
        old = self.cycle(timezone.now() - timedelta(days=2))
        selected = self.cycle(timezone.now())
        self.add_response(old, 5, "excluded old")
        for score in (1, 2, 2, 4):
            self.add_response(selected, score)
        response = self.client.get(self.url)
        expected = [
            {"score": 1, "count": 1}, {"score": 2, "count": 2}, {"score": 3, "count": 0},
            {"score": 4, "count": 1}, {"score": 5, "count": 0},
        ]
        self.assertEqual(response.context["response_total"], 4)
        self.assertEqual(response.context["average_score"], 2.25)
        self.assertContains(response, "2.3")
        self.assertEqual(response.context["bars"], expected)
        self.assertEqual(sum(bar["count"] for bar in expected), 4)
        for score in range(1, 6):
            self.assertContains(response, f'<span class="distribution-label">{score}</span>', html=True)
        self.assertEqual(list(selected.responses.order_by("id").values_list("score", flat=True)), [1, 2, 2, 4])

    def test_comments_filter_other_cycles_blank_values_and_order_equal_times_by_id(self):
        old_cycle = self.cycle(timezone.now() - timedelta(days=2))
        selected = self.cycle(timezone.now())
        self.add_response(old_cycle, 5, "old-cycle-comment")
        self.add_response(selected, 1, "")
        self.add_response(selected, 2, "   \n\t")
        first = self.add_response(selected, 3, "first equal-time comment")
        second = self.add_response(selected, 4, "second equal-time comment")
        equal_time = timezone.now() - timedelta(minutes=5)
        Response.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=equal_time)
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertNotContains(response, "old-cycle-comment")
        self.assertNotContains(response, "   \n\t")
        self.assertLess(content.index("second equal-time comment"), content.index("first equal-time comment"))
        self.assertContains(response, 'class="anonymous-label"', count=2)

    def test_html_comment_is_escaped_and_private_values_are_absent(self):
        cycle = self.cycle(timezone.now())
        raw_comment = '<script>alert("unsafe")</script>'
        saved = self.add_response(cycle, 4, raw_comment)
        response = self.client.get(self.url)
        self.assertContains(response, escape(raw_comment))
        self.assertNotContains(response, raw_comment)
        for private in (saved.network_hash, saved.device_hash, cycle.token, reverse("feedback_form", args=[cycle.token])):
            self.assertNotContains(response, private)

    def test_zero_responses_shows_dates_zero_metrics_five_buckets_and_no_comments(self):
        cycle = self.cycle(timezone.now())
        response = self.client.get(self.url)
        self.assertEqual(response.context["response_total"], 0)
        self.assertIsNone(response.context["average_score"])
        self.assertContains(response, '<div class="stat-value">—</div>', html=True)
        self.assertContains(response, '<span class="distribution-count">0</span>', count=5, html=True)
        self.assertContains(response, "No comments yet")
        self.assertContains(response, date_format(timezone.localtime(cycle.opens_at), "M j, Y, g:i A"))

    def test_only_blank_comments_keeps_metrics_and_shows_no_comments(self):
        cycle = self.cycle(timezone.now())
        self.add_response(cycle, 2, "")
        self.add_response(cycle, 4, " \n ")
        response = self.client.get(self.url)
        self.assertEqual(response.context["response_total"], 2)
        self.assertContains(response, "3.0")
        self.assertContains(response, "No comments yet")

    def test_no_cycle_is_clean_200_without_fabricated_data(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.name)
        self.assertContains(response, "No feedback cycles yet")
        for absent in ("Opens:", "Average score", "Responses", "Score distribution"):
            self.assertNotContains(response, absent)

    def test_authorized_inactive_project_is_visible_and_labelled(self):
        self.project.is_active = False
        self.project.save(update_fields=["is_active"])
        self.cycle(timezone.now())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.name)
        self.assertContains(response, "Inactive project")

    def test_unauthorized_and_missing_projects_are_non_disclosing_404(self):
        hidden = Project.objects.create(name="Secret hidden project", description="Secret description")
        hidden_cycle = self.cycle(timezone.now(), project=hidden)
        self.add_response(hidden_cycle, 5, "Secret response comment")
        for project_id in (hidden.id, hidden.id + 9999):
            with self.subTest(project_id=project_id):
                response = self.client.get(reverse("project_dashboard", args=[project_id]))
                self.assertEqual(response.status_code, 404)
                for secret in (hidden.name, hidden.description, "Secret response comment", hidden_cycle.token):
                    self.assertNotContains(response, secret, status_code=404)
