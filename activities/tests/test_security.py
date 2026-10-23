import hashlib
import hmac
import json
from unittest import mock

from django.contrib.auth.models import User
from django.template import Context, Template
from django.test import TestCase, override_settings


class JsonJsFilterTests(TestCase):
    def render(self, value):
        return Template("{% load custom_filters %}{{ value|json_js }}").render(Context({"value": value}))

    def test_escapes_script_breakout_in_json_string(self):
        out = self.render(json.dumps({"name": "</script><script>alert(1)</script>"}))
        self.assertNotIn("<", out)
        self.assertEqual(json.loads(out)["name"], "</script><script>alert(1)</script>")

    def test_serializes_python_objects(self):
        out = self.render([{"name": "A & <B>"}])
        self.assertNotIn("<", out)
        self.assertEqual(json.loads(out), [{"name": "A & <B>"}])


class StravaWebhookDeleteTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com")
        self.owner.socialaccount_set.create(provider="strava", uid="111")
        self.other = User.objects.create_user("other", "other@example.com")
        self.other.socialaccount_set.create(provider="strava", uid="222")

    def post(self, owner_id, object_id):
        payload = {"object_type": "activity", "aspect_type": "delete", "owner_id": owner_id, "object_id": object_id}
        return self.client.post("/activities/strava/webhook/", json.dumps(payload), content_type="application/json")

    @mock.patch("activities.views.webhook.delete_strava_activity_task")
    def test_delete_for_another_users_activity_is_ignored(self, task):
        with mock.patch("activities.views.webhook.Activity.objects.filter") as qs:
            qs.return_value.exists.return_value = False
            self.post(owner_id=222, object_id=999)
            qs.assert_called_once_with(user=self.other, strava_id=999)
        task.delay.assert_not_called()

    @mock.patch("activities.views.webhook.delete_strava_activity_task")
    def test_delete_is_deferred_to_verification_task(self, task):
        with mock.patch("activities.views.webhook.Activity.objects.filter") as qs:
            qs.return_value.exists.return_value = True
            self.post(owner_id=111, object_id=999)
        task.delay.assert_called_once_with(self.owner.id, 999)

    @mock.patch("activities.tasks.load_activity")
    def test_task_keeps_activity_that_still_exists_on_strava(self, load):
        from activities.tasks import delete_strava_activity_task

        with mock.patch("activities.tasks.Activity.objects.filter") as qs:
            delete_strava_activity_task(self.owner.id, 999)
        qs.assert_not_called()

    @mock.patch("activities.tasks.load_activity")
    def test_task_deletes_activity_gone_from_strava(self, load):
        from stravalib.exc import ObjectNotFound
        from activities.tasks import delete_strava_activity_task

        load.side_effect = ObjectNotFound("gone")
        with mock.patch("activities.tasks.Activity.objects.filter") as qs:
            qs.return_value.delete.return_value = (1, {})
            delete_strava_activity_task(self.owner.id, 999)
        qs.assert_called_once_with(user=self.owner, strava_id=999)


class BuyMeACoffeeWebhookTests(TestCase):
    body = json.dumps({"supporter_email": "x@example.com", "amount": 100}).encode()

    @override_settings(BUYMEACOFFEE_WEBHOOK_SECRET="")
    def test_rejected_when_secret_not_configured(self):
        resp = self.client.post("/webhooks/buymeacoffee/", self.body, content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    @override_settings(BUYMEACOFFEE_WEBHOOK_SECRET="s3cret")
    def test_rejected_with_bad_signature(self):
        resp = self.client.post(
            "/webhooks/buymeacoffee/", self.body, content_type="application/json", HTTP_X_SIGNATURE_SHA256="bad"
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(BUYMEACOFFEE_WEBHOOK_SECRET="s3cret")
    def test_accepts_valid_signature(self):
        sig = hmac.new(b"s3cret", self.body, hashlib.sha256).hexdigest()
        resp = self.client.post(
            "/webhooks/buymeacoffee/", self.body, content_type="application/json", HTTP_X_SIGNATURE_SHA256=sig
        )
        self.assertNotEqual(resp.status_code, 403)
