import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import FeedbackCycle, Project, Response
from .views import DEVICE_COOKIE_MAX_AGE, MISSING_NETWORK_IDENTIFIER


class DuplicateProtectionTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Duplicate protection")
        self.cycle = self.make_cycle()
        self.url = reverse("feedback_form", args=[self.cycle.token])

    def make_cycle(self):
        return FeedbackCycle.objects.create(
            project=self.project,
            opens_at=timezone.now() - timedelta(hours=1),
            closes_at=timezone.now() + timedelta(hours=1),
        )

    def submit(self, client=None, url=None, network="192.0.2.1", **extra):
        request = {"REMOTE_ADDR": network or ""}
        request.update(extra)
        return (client or self.client).post(url or self.url, {"score": "4"}, **request)

    def assert_duplicate(self, response, expected_count=1):
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Unable to submit", status_code=409)
        self.assertNotContains(response, "Submit anonymous feedback", status_code=409)
        self.assertNotContains(response, "network identifier", status_code=409)
        self.assertNotContains(response, "device identifier", status_code=409)
        page = response.content.decode()
        for saved in Response.objects.all():
            self.assertNotIn(saved.network_hash, page)
            self.assertNotIn(saved.device_hash, page)
        self.assertEqual(Response.objects.count(), expected_count)

    @override_settings(FEEDBACK_HASH_SALT="first-test-salt")
    def test_success_stores_salted_lowercase_sha256_hashes_not_raw_values(self):
        raw_device = "known-device"
        raw_network = "198.51.100.10"
        self.client.cookies["pulse_device"] = raw_device

        self.submit(network=raw_network)

        saved = Response.objects.get()
        expected_network = hashlib.sha256(f"first-test-salt:{raw_network}".encode()).hexdigest()
        expected_device = hashlib.sha256(f"first-test-salt:{raw_device}".encode()).hexdigest()
        self.assertEqual(saved.network_hash, expected_network)
        self.assertEqual(saved.device_hash, expected_device)
        for value in (saved.network_hash, saved.device_hash):
            self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertNotEqual(saved.network_hash, raw_network)
        self.assertNotEqual(saved.device_hash, raw_device)

    def test_changing_salt_changes_hash_for_same_raw_identifiers(self):
        client = Client()
        client.cookies["pulse_device"] = "same-device"
        with override_settings(FEEDBACK_HASH_SALT="salt-one"):
            self.submit(client=client, network="198.51.100.20")
        first = Response.objects.get()
        second_cycle = self.make_cycle()
        with override_settings(FEEDBACK_HASH_SALT="salt-two"):
            self.submit(
                client=client,
                url=reverse("feedback_form", args=[second_cycle.token]),
                network="198.51.100.20",
            )
        second = Response.objects.get(cycle=second_cycle)
        self.assertNotEqual(first.network_hash, second.network_hash)
        self.assertNotEqual(first.device_hash, second.device_hash)

    @override_settings(DEBUG=False)
    def test_new_device_cookie_is_set_only_on_success_with_required_attributes(self):
        invalid = self.client.post(self.url, {"score": "invalid"}, REMOTE_ADDR="192.0.2.30")
        self.assertNotIn("pulse_device", invalid.cookies)
        self.assertNotIn("pulse_device", self.client.cookies)
        self.assertEqual(Response.objects.count(), 0)

        success = self.submit(network="192.0.2.30")

        cookie = success.cookies["pulse_device"]
        self.assertTrue(cookie.value)
        self.assertEqual(int(cookie["max-age"]), DEVICE_COOKIE_MAX_AGE)
        self.assertEqual(cookie["path"], "/")
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertTrue(cookie["secure"])

    def test_existing_device_cookie_is_reused_on_a_different_cycle(self):
        raw_device = "existing-opaque-device"
        self.client.cookies["pulse_device"] = raw_device
        self.submit(network="192.0.2.40")
        second = self.make_cycle()

        response = self.submit(url=reverse("feedback_form", args=[second.token]), network="192.0.2.41")

        self.assertEqual(response.cookies["pulse_device"].value, raw_device)

    def test_same_network_with_different_devices_blocks_get_and_post(self):
        first = Client()
        first.cookies["pulse_device"] = "device-one"
        self.submit(client=first, network="192.0.2.50")
        for method in ("get", "post"):
            with self.subTest(method=method):
                other = Client()
                other.cookies["pulse_device"] = f"other-{method}"
                request = getattr(other, method)
                response = request(self.url, {"score": "5"}, REMOTE_ADDR="192.0.2.50")
                self.assert_duplicate(response)

    def test_same_device_with_different_networks_blocks_get_and_post(self):
        first = Client()
        first.cookies["pulse_device"] = "shared-device"
        self.submit(client=first, network="192.0.2.60")
        for method in ("get", "post"):
            with self.subTest(method=method):
                other = Client()
                other.cookies["pulse_device"] = "shared-device"
                request = getattr(other, method)
                response = request(self.url, {"score": "5"}, REMOTE_ADDR=f"192.0.2.{61 if method == 'get' else 62}")
                self.assert_duplicate(response)

    def test_identifiers_are_scoped_to_cycle(self):
        self.client.cookies["pulse_device"] = "reusable-device"
        self.submit(network="192.0.2.70")
        second = self.make_cycle()

        response = self.submit(url=reverse("feedback_form", args=[second.token]), network="192.0.2.70")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Response.objects.count(), 2)

    def test_two_distinct_network_and_device_pairs_are_both_accepted(self):
        first = Client()
        first.cookies["pulse_device"] = "first-device"
        second = Client()
        second.cookies["pulse_device"] = "second-device"

        self.submit(client=first, network="192.0.2.80")
        response = self.submit(client=second, network="192.0.2.81")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Response.objects.count(), 2)

    def test_database_constraints_reject_each_matching_identifier(self):
        Response.objects.create(
            cycle=self.cycle,
            score=3,
            network_hash="a" * 64,
            device_hash="b" * 64,
        )
        conflicts = (
            {"network_hash": "a" * 64, "device_hash": "c" * 64},
            {"network_hash": "d" * 64, "device_hash": "b" * 64},
        )
        for fields in conflicts:
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                Response.objects.create(cycle=self.cycle, score=4, **fields)
        self.assertEqual(Response.objects.count(), 1)

    def test_racing_conflict_returns_generic_duplicate_page(self):
        raw_network = "192.0.2.90"
        raw_device = "racing-device"
        self.client.cookies["pulse_device"] = raw_device
        Response.objects.create(
            cycle=self.cycle,
            score=3,
            network_hash=hashlib.sha256(f"{self._salt()}:{raw_network}".encode()).hexdigest(),
            device_hash=hashlib.sha256(f"{self._salt()}:{raw_device}".encode()).hexdigest(),
        )
        with patch("django.db.models.query.QuerySet.exists", return_value=False):
            response = self.submit(network=raw_network)
        self.assert_duplicate(response)

    def test_attacker_selected_cookie_is_only_opaque_hash_input(self):
        raw_cookie = "<script>alert('raw-device')</script>"
        self.client.cookies["pulse_device"] = raw_cookie

        response = self.submit(network="192.0.2.100")

        saved = Response.objects.get()
        self.assertNotIn(raw_cookie, response.content.decode())
        self.assertNotEqual(saved.device_hash, raw_cookie)
        self.assertNotIn(raw_cookie, (saved.comment, saved.network_hash, saved.device_hash))

    def test_missing_network_uses_nonempty_salted_fallback_and_fails_closed(self):
        first = Client()
        first.cookies["pulse_device"] = "first-missing-network"
        self.submit(client=first, network=None)
        saved = Response.objects.get()
        self.assertEqual(saved.network_hash, hashlib.sha256(f"{self._salt()}:{MISSING_NETWORK_IDENTIFIER}".encode()).hexdigest())
        self.assertTrue(saved.network_hash)

        second = Client()
        second.cookies["pulse_device"] = "second-missing-network"
        response = self.submit(client=second, network=None)
        self.assert_duplicate(response)

    def test_forwarded_header_cannot_spoof_direct_network_address(self):
        first = Client()
        first.cookies["pulse_device"] = "forwarded-first"
        self.submit(client=first, network="192.0.2.110", HTTP_X_FORWARDED_FOR="198.51.100.1")
        second = Client()
        second.cookies["pulse_device"] = "forwarded-second"

        response = self.submit(client=second, network="192.0.2.110", HTTP_X_FORWARDED_FOR="198.51.100.2")

        self.assert_duplicate(response)

    def test_invalid_form_does_not_save_or_set_cookie_then_can_be_corrected(self):
        response = self.client.post(self.url, {"score": "0"}, REMOTE_ADDR="192.0.2.120")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Response.objects.count(), 0)
        self.assertNotIn("pulse_device", response.cookies)

        corrected = self.submit(network="192.0.2.120")
        self.assertEqual(corrected.status_code, 302)
        self.assertEqual(Response.objects.count(), 1)

    @staticmethod
    def _salt():
        from django.conf import settings

        return settings.FEEDBACK_HASH_SALT
