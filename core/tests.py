import importlib
from datetime import timedelta
from unittest import mock

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import RequestFactory, TestCase
from django.utils import timezone

from activities.models import Activity
from core.account_adapter import AsyncEmailAccountAdapter
from core.models import UserProfile
from core.tasks import purge_unverified_users


def make_activity(user):
    now = timezone.now()
    return Activity.objects.create(
        user=user,
        name="Ski day",
        strava_id=user.pk,
        timestamp=now,
        start_time=now,
        total_elapsed_time=timedelta(hours=1),
        total_timer_time=timedelta(hours=1),
        total_distance=1000,
        start_position=Point(7.1, 46.5, srid=4326),
        sport_profile_name="AlpineSki",
    )


class SignupHoneypotTests(TestCase):
    def signup(self, **extra):
        data = {"email": "user@example.com", "password1": "S3cure-pass-123", "password2": "S3cure-pass-123"}
        return self.client.post("/accounts/signup/", {**data, **extra})

    @mock.patch("core.tasks.send_email_async.delay")
    def test_valid_signup_creates_user(self, _send_email):
        # Control: the same payload without the honeypot is a valid signup
        self.signup()
        self.assertTrue(User.objects.filter(email="user@example.com").exists())

    def test_honeypot_submission_creates_no_user(self):
        resp = self.signup(website="http://spam.example")
        self.assertIn(resp.status_code, (200, 302))
        self.assertFalse(User.objects.filter(email="user@example.com").exists())

    def test_signup_form_renders_honeypot_field(self):
        resp = self.client.get("/accounts/signup/")
        self.assertContains(resp, 'name="website"')


class ClientIpTests(TestCase):
    def test_uses_proxy_appended_forwarded_for_entry(self):
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(AsyncEmailAccountAdapter(request).get_client_ip(request), "203.0.113.7")

    def test_falls_back_to_remote_addr(self):
        request = RequestFactory().get("/", REMOTE_ADDR="198.51.100.2")
        self.assertEqual(AsyncEmailAccountAdapter(request).get_client_ip(request), "198.51.100.2")


class PurgeUnverifiedUsersTests(TestCase):
    def make_user(self, name, days_old=30, **kwargs):
        user = User.objects.create_user(name, f"{name}@example.com", **kwargs)
        User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=days_old))
        return user

    def test_purges_only_stale_unverified_inactive_accounts(self):
        spam = self.make_user("spam")
        EmailAddress.objects.create(user=spam, email=spam.email, verified=False, primary=True)
        recent = self.make_user("recent", days_old=1)
        verified = self.make_user("verified")
        EmailAddress.objects.create(user=verified, email=verified.email, verified=True, primary=True)
        strava = self.make_user("strava")
        SocialAccount.objects.create(user=strava, provider="strava", uid="1")
        active = self.make_user("active")
        make_activity(active)
        staff = self.make_user("staff", is_staff=True)

        purge_unverified_users()

        remaining = set(User.objects.values_list("username", flat=True))
        self.assertEqual(
            remaining, {recent.username, verified.username, strava.username, active.username, staff.username}
        )


class DeleteUsersWithoutActivitiesMigrationTests(TestCase):
    def test_deletes_users_without_activities_but_keeps_protected_accounts(self):
        migration = importlib.import_module("core.migrations.0014_delete_users_without_activities")
        active = User.objects.create_user("active")
        make_activity(active)
        User.objects.create_user("spam1")
        User.objects.create_user("spam2")
        User.objects.create_user("admin", is_staff=True, is_superuser=True)
        premium = User.objects.create_user("premium")
        UserProfile.objects.update_or_create(user=premium, defaults={"is_premium": True})

        migration.delete_users_without_activities(django_apps, None)

        self.assertEqual(set(User.objects.values_list("username", flat=True)), {"active", "admin", "premium"})
