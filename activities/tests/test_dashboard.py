from datetime import date, datetime, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from activities.models import Activity
from activities.utils.seasons import get_season_dates
from core.models import UserProfile


def make_activity(user, when, strava_id):
    return Activity.objects.create(
        user=user,
        name="Ski day",
        strava_id=strava_id,
        timestamp=when,
        start_time=when,
        total_elapsed_time=timedelta(hours=5),
        total_timer_time=timedelta(hours=4),
        total_distance=30000,
        total_descent=4000,
        start_position=Point(7.1, 46.5, srid=4326),
        sport_profile_name="AlpineSki",
    )


class DashboardOffSeasonTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("skier", "skier@example.com", "pw")
        UserProfile.objects.create(user=self.user, profile_confirmed=True)
        self.client.force_login(self.user)

    def test_shows_latest_season_when_current_season_has_no_activities(self):
        # A year ago is always in the previous season, so the current season is empty
        a_year_ago = timezone.now() - timedelta(days=365)
        make_activity(self.user, a_year_ago, 1)
        make_activity(self.user, a_year_ago + timedelta(days=1), 2)

        resp = self.client.get("/home/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_stats"]["total_num_activities"], 2)
        self.assertNotContains(resp, "No activities yet")

    def test_user_without_activities_sees_empty_state(self):
        resp = self.client.get("/home/")
        self.assertContains(resp, "No activities yet")


class SeasonDatesTests(TestCase):
    def dates_on(self, today, user=None, current=True):
        with mock.patch("activities.utils.seasons.timezone.localdate", return_value=today):
            return get_season_dates(current=current, user=user)

    def test_season_end_includes_the_whole_last_day(self):
        _, end = self.dates_on(date(2026, 3, 1))
        self.assertGreaterEqual(end, datetime(2026, 6, 30, 23, 59, 59))
        self.assertLess(end, datetime(2026, 7, 1))

    def test_custom_season_start_day_is_respected(self):
        user = User.objects.create_user("custom")
        UserProfile.objects.create(user=user, season_start_month=11, season_start_day=15)

        start, end = self.dates_on(date(2026, 11, 10), user=user)

        # 10 Nov is before the 15 Nov start, so it still belongs to the season that began in 2025
        self.assertEqual(start, datetime(2025, 11, 15))
        self.assertEqual(end.date(), date(2026, 11, 14))

    def test_previous_season(self):
        start, end = self.dates_on(date(2026, 10, 23), current=False)
        self.assertEqual(start, datetime(2025, 7, 1))
        self.assertEqual(end.date(), date(2026, 6, 30))


class DashboardSkiAreaTests(TestCase):
    def test_activities_without_ski_area_do_not_break_dashboard(self):
        user = User.objects.create_user("noarea", "noarea@example.com", "pw")
        UserProfile.objects.create(user=user, profile_confirmed=True)
        self.client.force_login(user)
        make_activity(user, timezone.now(), 10)  # no ski_area

        resp = self.client.get("/home/")

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context["skiarea"])
