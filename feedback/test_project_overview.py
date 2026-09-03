from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedbackCycle, Project, Response


class ProjectOverviewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.lead = User.objects.create_user("lead")
        self.second_lead = User.objects.create_user("second-lead")
        self.staff = User.objects.create_user("staff", is_staff=True)
        self.url = reverse("dashboard")

    def project(self, name, *, active=True, leads=()):
        project = Project.objects.create(name=name, is_active=active)
        project.leads.add(*leads)
        return project

    def cycle(self, project, offset):
        now = timezone.now()
        windows = {
            "closed": (now - timedelta(days=3), now - timedelta(days=2)),
            "open": (now - timedelta(hours=1), now + timedelta(hours=1)),
            "future": (now + timedelta(days=2), now + timedelta(days=3)),
        }
        opens_at, closes_at = windows[offset]
        return FeedbackCycle.objects.create(project=project, opens_at=opens_at, closes_at=closes_at)

    def response(self, cycle, score, suffix):
        return Response.objects.create(
            cycle=cycle,
            score=score,
            comment=f"private-comment-{suffix}",
            network_hash=f"{suffix:064x}",
            device_hash=f"{suffix + 1000:064x}",
        )

    def login(self, user):
        self.client.force_login(user)
        return self.client.get(self.url)

    def test_lead_sees_each_active_assigned_project_once_and_no_others(self):
        assigned = self.project("Assigned", leads=(self.lead, self.second_lead))
        unassigned = self.project("Unassigned", leads=(self.second_lead,))
        inactive = self.project("Inactive assigned", active=False, leads=(self.lead,))

        response = self.login(self.lead)

        self.assertContains(response, "Project overview")
        self.assertContains(response, assigned.name, count=1)
        self.assertNotContains(response, unassigned.name)
        self.assertNotContains(response, inactive.name)
        self.assertContains(response, 'class="project-row"', count=1)

    def test_staff_sees_every_active_project_once_without_assignment(self):
        first = self.project("First")
        second = self.project("Second", leads=(self.lead, self.second_lead))
        inactive = self.project("Inactive", active=False)

        response = self.login(self.staff)

        self.assertContains(response, first.name, count=1)
        self.assertContains(response, second.name, count=1)
        self.assertNotContains(response, inactive.name)
        self.assertContains(response, 'class="project-row"', count=2)

    def test_all_cycles_contribute_once_to_exact_count_and_average(self):
        project = self.project("All cycle totals", leads=(self.lead, self.second_lead))
        for index, (window, score) in enumerate((("closed", 1), ("open", 2), ("future", 5)), start=1):
            self.response(self.cycle(project, window), score, index)

        response = self.login(self.lead)

        shown = response.context["projects"].get(pk=project.pk)
        self.assertEqual(shown.response_count, 3)
        self.assertEqual(shown.average_score, 8 / 3)
        self.assertContains(response, "2.7")
        self.assertContains(response, ">3</td>")

    def test_average_uses_normal_one_decimal_rounding_without_changing_scores(self):
        project = self.project("Rounding", leads=(self.lead,))
        cycle = self.cycle(project, "open")
        for score, suffix in zip((1, 2, 3, 3), range(10, 14)):
            self.response(cycle, score, suffix)

        response = self.login(self.lead)

        self.assertContains(response, "2.3")
        self.assertEqual(list(cycle.responses.order_by("score").values_list("score", flat=True)), [1, 2, 3, 3])

    def test_cycles_without_responses_and_projects_without_cycles_show_placeholders(self):
        with_empty_cycle = self.project("Empty cycle", leads=(self.lead,))
        self.cycle(with_empty_cycle, "open")
        without_cycle = self.project("No cycle", leads=(self.lead,))

        response = self.login(self.lead)

        for project in (with_empty_cycle, without_cycle):
            shown = response.context["projects"].get(pk=project.pk)
            self.assertEqual(shown.response_count, 0)
            self.assertIsNone(shown.average_score)
        self.assertContains(response, '<span class="mini-score">—</span>', count=2, html=True)
        self.assertContains(response, "<td>0</td>", count=2, html=True)

    def test_project_names_link_to_corresponding_detail_routes(self):
        project = self.project("Linked project", leads=(self.lead,))

        response = self.login(self.lead)

        expected = f'<a class="project-name" href="{reverse("project_dashboard", args=[project.id])}">{project.name}</a>'
        self.assertContains(response, expected, html=True)

    def test_order_is_case_insensitive_then_by_id_for_equal_names(self):
        names = ("beta", "Alpha", "alpha", "Gamma")
        projects = [self.project(name, leads=(self.lead,)) for name in names]

        response = self.login(self.lead)

        displayed = list(response.context["projects"])
        self.assertEqual(displayed, [projects[1], projects[2], projects[0], projects[3]])

    def test_role_specific_empty_states_have_no_project_rows(self):
        inactive = self.project("Hidden inactive", active=False, leads=(self.lead,))
        for user, message in (
            (self.lead, "No active projects are assigned to this account"),
            (self.staff, "No active projects are available"),
        ):
            with self.subTest(user=user):
                response = self.login(user)
                self.assertContains(response, message)
                self.assertNotContains(response, 'class="project-row"')
                self.assertNotContains(response, inactive.name)

    def test_overview_excludes_response_level_and_private_metadata(self):
        project = self.project("Privacy", leads=(self.lead,))
        cycle = self.cycle(project, "open")
        saved = self.response(cycle, 4, 99)

        response = self.login(self.lead)

        self.assertNotContains(response, saved.comment)
        self.assertNotContains(response, saved.network_hash)
        self.assertNotContains(response, saved.device_hash)
        self.assertNotContains(response, cycle.token)
        self.assertNotContains(response, "Score 4")
