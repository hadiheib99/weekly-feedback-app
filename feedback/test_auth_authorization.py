from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedbackCycle, Project
from .views import _visible_projects


class AuthenticationAuthorizationTests(TestCase):
    password = "valid-test-password"

    def setUp(self):
        User = get_user_model()
        self.lead = User.objects.create_user("lead", password=self.password)
        self.other = User.objects.create_user("other", password=self.password)
        self.staff = User.objects.create_user("staff", password=self.password, is_staff=True)
        self.active = Project.objects.create(name="Assigned active", description="Active secret")
        self.inactive = Project.objects.create(
            name="Assigned inactive",
            description="Inactive secret",
            is_active=False,
        )
        self.unassigned = Project.objects.create(name="Unassigned secret", description="Hidden details")
        self.active.leads.add(self.lead)
        self.inactive.leads.add(self.lead)
        for project in (self.active, self.inactive, self.unassigned):
            FeedbackCycle.objects.create(
                project=project,
                opens_at=timezone.now() - timedelta(hours=1),
                closes_at=timezone.now() + timedelta(hours=1),
            )

    def test_anonymous_internal_routes_redirect_to_login_with_exact_return_url(self):
        routes = (reverse("dashboard"), reverse("project_dashboard", args=[self.active.id]))
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertRedirects(response, f"{reverse('login')}?next={route}")

    def test_login_page_has_labelled_credentials_and_only_sign_in_flow(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, '<label class="question-label" for="id_username">Username</label>', html=True)
        self.assertContains(response, '<label class="question-label" for="id_password">Password</label>', html=True)
        self.assertContains(response, "Sign in")
        self.assertNotContains(response, "Register")
        self.assertNotContains(response, "passwordless")

    def test_valid_login_uses_safe_local_return_url_or_dashboard_default(self):
        detail = reverse("project_dashboard", args=[self.active.id])
        response = self.client.post(reverse("login"), {"username": "lead", "password": self.password, "next": detail})
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        self.client.logout()

        response = self.client.post(reverse("login"), {"username": "lead", "password": self.password})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_invalid_credentials_are_generic_and_leave_user_signed_out(self):
        cases = (
            {"username": "unknown", "password": self.password},
            {"username": "lead", "password": "incorrect-password"},
            {"username": "", "password": ""},
        )
        for credentials in cases:
            with self.subTest(credentials=credentials):
                response = self.client.post(reverse("login"), credentials)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "The username or password is incorrect.")
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_sign_out_control_ends_session(self):
        self.client.force_login(self.lead)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, "Sign out")
        self.assertContains(dashboard, f'action="{reverse("logout")}"')

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        protected = self.client.get(reverse("dashboard"))
        self.assertRedirects(protected, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_unsafe_return_destinations_are_ignored(self):
        for destination in ("https://evil.example/steal", "//evil.example/steal"):
            with self.subTest(destination=destination):
                response = self.client.post(
                    reverse("login"),
                    {"username": "lead", "password": self.password, "next": destination},
                )
                self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
                self.client.logout()

    def test_reusable_visibility_policy_includes_inactive_and_staff_sees_all(self):
        self.assertQuerySetEqual(
            _visible_projects(self.lead).order_by("id"),
            [self.active, self.inactive],
        )
        self.assertQuerySetEqual(
            _visible_projects(self.staff).order_by("id"),
            [self.active, self.inactive, self.unassigned],
        )
        self.assertFalse(_visible_projects(self.other).exists())

    def test_lead_can_open_each_assigned_project_including_inactive(self):
        self.client.force_login(self.lead)
        for project in (self.active, self.inactive):
            with self.subTest(project=project):
                response = self.client.get(reverse("project_dashboard", args=[project.id]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, project.name)

    def test_staff_can_open_every_project_without_assignment_even_without_cycle(self):
        no_cycle = Project.objects.create(name="No cycle", is_active=False)
        self.client.force_login(self.staff)
        for project in (self.active, self.inactive, self.unassigned, no_cycle):
            with self.subTest(project=project):
                response = self.client.get(reverse("project_dashboard", args=[project.id]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, project.name)

    def test_unassigned_and_missing_projects_have_same_non_leaking_not_found_result(self):
        self.client.force_login(self.lead)
        unauthorized = self.client.get(reverse("project_dashboard", args=[self.unassigned.id]))
        missing = self.client.get(reverse("project_dashboard", args=[self.unassigned.id + 9999]))

        for response in (unauthorized, missing):
            self.assertEqual(response.status_code, 404)
            self.assertContains(response, "Not Found", status_code=404)
            for secret in (self.unassigned.name, self.unassigned.description, "Hidden details"):
                self.assertNotContains(response, secret, status_code=404)

    def test_user_with_no_assignments_can_open_overview_but_no_details(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("project_dashboard", args=[self.active.id])).status_code, 404)

    def test_assignment_changes_take_effect_on_next_request(self):
        self.client.force_login(self.other)
        url = reverse("project_dashboard", args=[self.active.id])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.active.leads.add(self.other)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.active.leads.remove(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_public_routes_remain_accessible_without_login(self):
        cycle = self.active.cycles.get()
        public_routes = (
            (reverse("home"), 302),
            (reverse("feedback_form", args=[cycle.token]), 200),
            (reverse("feedback_thanks", args=[cycle.token]), 200),
        )
        for route, expected_status in public_routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn(reverse("login"), response.get("Location", ""))

        future = FeedbackCycle.objects.create(
            project=self.active,
            opens_at=timezone.now() + timedelta(hours=1),
            closes_at=timezone.now() + timedelta(hours=2),
        )
        unavailable = self.client.get(reverse("feedback_form", args=[future.token]))
        self.assertEqual(unavailable.status_code, 403)
        self.assertNotIn(reverse("login"), unavailable.get("Location", ""))
