from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import FeedbackCycleAdmin, ProjectAdmin, ResponseAdmin
from .models import FeedbackCycle, Project, Response


class FeedbackAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser("root", "root@example.test", "password")
        self.lead = User.objects.create_user("lead", "lead@example.test", "password")
        self.project = Project.objects.create(name="Admin project", description="Searchable description")
        self.project.leads.add(self.lead)
        self.cycle = FeedbackCycle.objects.create(
            project=self.project,
            opens_at=timezone.now() - timedelta(hours=1),
            closes_at=timezone.now() + timedelta(hours=1),
        )
        self.response = Response.objects.create(
            cycle=self.cycle,
            score=4,
            comment="<b>plain participant text</b>",
            network_hash="a" * 64,
            device_hash="b" * 64,
        )

    def login_superuser(self):
        self.client.force_login(self.superuser)

    def test_all_models_are_registered_with_expected_admin_classes(self):
        self.assertIsInstance(admin.site._registry[Project], ProjectAdmin)
        self.assertIsInstance(admin.site._registry[FeedbackCycle], FeedbackCycleAdmin)
        self.assertIsInstance(admin.site._registry[Response], ResponseAdmin)

    def test_project_admin_configuration_and_search_deduplicates_multiple_matching_leads(self):
        model_admin = admin.site._registry[Project]
        self.assertEqual(model_admin.list_display, ("name", "is_active", "created_at"))
        self.assertEqual(model_admin.list_filter, ("is_active",))
        self.assertEqual(model_admin.filter_horizontal, ("leads",))
        second = get_user_model().objects.create_user("lead-two", "lead-two@example.test")
        self.project.leads.add(second)
        self.login_superuser()

        response = self.client.get(reverse("admin:feedback_project_changelist"), {"q": "lead"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].result_list), [self.project])
        self.assertContains(response, self.project.name, count=1)
        self.assertContains(response, "is_active__exact")

    def test_superuser_can_add_edit_assign_leads_and_delete_project_with_confirmation(self):
        self.login_superuser()
        second_lead = get_user_model().objects.create_user("second-admin-lead")
        add_url = reverse("admin:feedback_project_add")
        added = self.client.post(add_url, {
            "name": "Created project", "description": "Created", "is_active": "on",
            "leads": [self.lead.pk, second_lead.pk],
            "_save": "Save",
        })
        created = Project.objects.get(name="Created project")
        self.assertEqual(added.status_code, 302)
        self.assertQuerySetEqual(created.leads.order_by("pk"), [self.lead, second_lead], ordered=False)
        self.client.force_login(self.lead)
        self.assertContains(self.client.get(reverse("dashboard")), created.name)
        self.login_superuser()

        change_url = reverse("admin:feedback_project_change", args=[created.pk])
        changed = self.client.post(change_url, {
            "name": "Renamed project", "description": "Changed", "is_active": "", "leads": [], "_save": "Save",
        })
        created.refresh_from_db()
        self.assertEqual(changed.status_code, 302)
        self.assertEqual(created.name, "Renamed project")
        self.assertFalse(created.is_active)
        self.assertFalse(created.leads.exists())
        change_page = self.client.get(change_url)
        self.assertContains(change_page, 'name="leads"')
        self.assertContains(change_page, "multiple")

        delete_url = reverse("admin:feedback_project_delete", args=[created.pk])
        confirmation = self.client.get(delete_url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "Are you sure")
        self.client.post(delete_url, {"post": "yes"})
        self.assertFalse(Project.objects.filter(pk=created.pk).exists())

    def test_project_search_supports_name_description_username_and_email(self):
        self.login_superuser()
        url = reverse("admin:feedback_project_changelist")
        for term in ("Admin project", "Searchable description", "lead", "lead@example.test"):
            with self.subTest(term=term):
                self.assertContains(self.client.get(url, {"q": term}), self.project.name)

    def test_cycle_admin_create_edit_readonly_token_validation_and_delete_confirmation(self):
        self.login_superuser()
        list_url = reverse("admin:feedback_feedbackcycle_changelist")
        listing = self.client.get(list_url)
        for heading in ("Project", "Opens at", "Closes at", "Currently open"):
            self.assertContains(listing, heading)
        filtered = self.client.get(list_url, {"project__id__exact": self.project.pk})
        self.assertContains(filtered, self.project.name)
        self.assertContains(self.client.get(list_url, {"q": self.project.name}), self.project.name)
        self.assertEqual(admin.site._registry[FeedbackCycle].date_hierarchy, "opens_at")

        opens = timezone.now() + timedelta(days=2)
        closes = opens + timedelta(hours=1)
        add_url = reverse("admin:feedback_feedbackcycle_add")
        created_response = self.client.post(add_url, {
            "project": self.project.pk,
            "opens_at_0": opens.date().isoformat(), "opens_at_1": opens.time().strftime("%H:%M:%S"),
            "closes_at_0": closes.date().isoformat(), "closes_at_1": closes.time().strftime("%H:%M:%S"),
            "_continue": "Save and continue editing",
        })
        created = FeedbackCycle.objects.exclude(pk=self.cycle.pk).get()
        self.assertRedirects(created_response, reverse("admin:feedback_feedbackcycle_change", args=[created.pk]), fetch_redirect_response=False)
        edit_page = self.client.get(reverse("admin:feedback_feedbackcycle_change", args=[created.pk]))
        self.assertContains(edit_page, created.token)
        self.assertNotContains(edit_page, 'name="token"')

        invalid = self.client.post(reverse("admin:feedback_feedbackcycle_change", args=[created.pk]), {
            "project": self.project.pk,
            "opens_at_0": opens.date().isoformat(), "opens_at_1": "12:00:00",
            "closes_at_0": opens.date().isoformat(), "closes_at_1": "11:00:00",
            "_save": "Save",
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Closing time must be after opening time")
        created.refresh_from_db()
        self.assertLess(created.opens_at, created.closes_at)

        delete_url = reverse("admin:feedback_feedbackcycle_delete", args=[created.pk])
        self.assertContains(self.client.get(delete_url), "Are you sure")
        self.client.post(delete_url, {"post": "yes"})
        self.assertFalse(FeedbackCycle.objects.filter(pk=created.pk).exists())

    def test_response_admin_is_view_only_configured_and_escapes_comment(self):
        self.login_superuser()
        model_admin = admin.site._registry[Response]
        self.assertEqual(model_admin.list_display, ("cycle", "score", "created_at"))
        self.assertEqual(model_admin.list_filter, ("score", "cycle__project"))
        self.assertEqual(model_admin.date_hierarchy, "created_at")
        list_page = self.client.get(reverse("admin:feedback_response_changelist"))
        for heading in ("Cycle", "Score", "Created at"):
            self.assertContains(list_page, heading)
        filtered = self.client.get(reverse("admin:feedback_response_changelist"), {"score__exact": 4})
        self.assertContains(filtered, str(self.cycle))
        self.assertContains(self.client.get(reverse("admin:feedback_response_changelist"), {"q": self.project.name}), str(self.cycle))

        detail_url = reverse("admin:feedback_response_change", args=[self.response.pk])
        detail = self.client.get(detail_url)
        for visible in (str(self.cycle), "plain participant text", self.response.network_hash, self.response.device_hash):
            self.assertContains(detail, visible)
        self.assertNotContains(detail, "<b>plain participant text</b>")
        self.assertNotContains(detail, "Save and continue editing")
        self.assertNotContains(detail, "Delete")
        self.assertEqual(self.client.get(reverse("admin:feedback_response_add")).status_code, 403)
        self.assertEqual(self.client.post(detail_url, {"score": 1}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:feedback_response_delete", args=[self.response.pk])).status_code, 403)

    def test_admin_pages_never_contain_raw_identifiers(self):
        self.login_superuser()
        raw_values = ("192.0.2.123", "raw-device-value")
        for url in (
            reverse("admin:index"), reverse("admin:feedback_response_changelist"),
            reverse("admin:feedback_response_change", args=[self.response.pk]),
        ):
            page = self.client.get(url)
            for raw in raw_values:
                self.assertNotContains(page, raw)

    def test_signed_out_and_nonstaff_users_cannot_access_admin_or_model_pages(self):
        urls = (
            reverse("admin:index"), reverse("admin:feedback_project_changelist"),
            reverse("admin:feedback_feedbackcycle_add"),
            reverse("admin:feedback_response_change", args=[self.response.pk]),
        )
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.lead)
        for url in urls:
            with self.subTest(url=url):
                page = self.client.get(url)
                self.assertIn(page.status_code, (302, 403))
                for secret in (self.project.name, self.response.network_hash, self.response.device_hash):
                    self.assertNotContains(page, secret, status_code=page.status_code)

    def test_staff_permissions_are_granular(self):
        staff = get_user_model().objects.create_user("limited", is_staff=True)
        self.client.force_login(staff)
        project_list = reverse("admin:feedback_project_changelist")
        self.assertEqual(self.client.get(project_list).status_code, 403)

        view = Permission.objects.get(codename="view_project")
        add = Permission.objects.get(codename="add_project")
        staff.user_permissions.add(view)
        self.assertEqual(self.client.get(project_list).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:feedback_project_add")).status_code, 403)
        view_only_detail = self.client.get(reverse("admin:feedback_project_change", args=[self.project.pk]))
        self.assertEqual(view_only_detail.status_code, 200)
        self.assertNotContains(view_only_detail, 'name="_save"')
        staff.user_permissions.add(add)
        self.assertEqual(self.client.get(reverse("admin:feedback_project_add")).status_code, 200)
        self.assertNotContains(
            self.client.get(reverse("admin:feedback_project_change", args=[self.project.pk])),
            'name="_save"',
        )
        self.assertNotContains(self.client.get(project_list), "Delete selected")

        staff.user_permissions.add(Permission.objects.get(codename="change_project"))
        self.assertEqual(self.client.get(reverse("admin:feedback_project_change", args=[self.project.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:feedback_project_delete", args=[self.project.pk])).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="delete_project"))
        self.assertEqual(self.client.get(reverse("admin:feedback_project_delete", args=[self.project.pk])).status_code, 200)

    def test_project_delete_confirmation_lists_cascading_related_records(self):
        self.login_superuser()
        confirmation = self.client.get(reverse("admin:feedback_project_delete", args=[self.project.pk]))
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "Are you sure")
        self.assertContains(confirmation, str(self.cycle))
        self.assertContains(confirmation, str(self.response))
        self.client.post(reverse("admin:feedback_project_delete", args=[self.project.pk]), {"post": "yes"})
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(FeedbackCycle.objects.filter(pk=self.cycle.pk).exists())
        self.assertFalse(Response.objects.filter(pk=self.response.pk).exists())
