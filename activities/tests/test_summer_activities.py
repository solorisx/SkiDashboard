"""
Tests for the summer-activity feature and its effect on season-pass costing.

Covers:
  * model creation / defaults
  * SeasonPass winter cost-per-day net of summer value
  * SeasonPass summer aggregates (total value, average value)
  * separation from the ski (Activity) pipeline
  * the summer-activity CRUD views
"""
from datetime import date, datetime, timedelta

from django.contrib.auth.models import User
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware
from djmoney.money import Money

from activities.models import Activity, SummerActivity, SummerActivityType
from cost.models import SeasonPass
from osm.models import SkiArea


def _make_ski_area(osm_id=900001, name="Test Resort"):
    polygon = Polygon((
        (7.0, 46.0), (7.1, 46.0), (7.1, 46.1), (7.0, 46.1), (7.0, 46.0),
    ))
    return SkiArea.objects.create(osm_id=osm_id, name=name, geom=MultiPolygon(polygon))


class SummerActivityModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", email="u@e.com", password="x")
        # Built-in types are seeded by migration 0027.
        self.type = SummerActivityType.objects.get(natural_key="hiking")

    def test_defaults_and_helpers(self):
        sa = SummerActivity.objects.create(
            user=self.user, name="Morning hike", activity_type=self.type, date=date(2024, 7, 1),
        )
        self.assertFalse(sa.is_covered)
        self.assertIsNone(sa.get_strava_url())

        sa.strava_id = 123456
        self.assertEqual(sa.get_strava_url(), "https://www.strava.com/activities/123456")

    def test_for_user_includes_globals(self):
        custom = SummerActivityType.objects.create(
            user=self.user, name="Paragliding", natural_key="u-paragliding",
        )
        other = User.objects.create_user(username="o", email="o@e.com", password="x")
        other_type = SummerActivityType.objects.create(
            user=other, name="Kayaking", natural_key="o-kayaking",
        )
        available = set(SummerActivityType.for_user(self.user).values_list("natural_key", flat=True))
        self.assertIn("hiking", available)        # global
        self.assertIn("u-paragliding", available)  # own
        self.assertNotIn("o-kayaking", available)  # someone else's
        del other_type, custom


class SeasonPassSummerCostingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", email="u@e.com", password="x")
        self.ski_area = _make_ski_area()
        self.type = SummerActivityType.objects.get(natural_key="hiking")

        self.pass_ = SeasonPass.objects.create(
            user=self.user,
            skiarea=self.ski_area,
            valid_from=date(2024, 1, 1),
            valid_until=date(2024, 12, 31),
            price=Money(600, "CHF"),
        )
        # Three winter ski activities covered by the pass.
        for day in (10, 20, 30):
            self._winter_activity(make_aware(datetime(2024, 1, day, 10, 0)))

    def _winter_activity(self, when):
        return Activity.objects.create(
            user=self.user,
            name="Ski day",
            type="AlpineSki",
            timestamp=when,
            start_time=when,
            total_elapsed_time=timedelta(hours=4),
            total_timer_time=timedelta(hours=3),
            total_distance=12000.0,
            start_position=Point(7.05, 46.05),
            sport_profile_name="Alpine Ski",
            ski_area=self.ski_area,
        )

    def _summer_activity(self, value, season_pass=None):
        return SummerActivity.objects.create(
            user=self.user, name="Hike", activity_type=self.type,
            date=date(2024, 7, 1), ski_area=self.ski_area,
            season_pass=season_pass, value=value,
        )

    def test_winter_only_without_summer(self):
        self.assertEqual(self.pass_.count_valid_activities(), 3)
        self.assertIsNone(self.pass_.total_summer_value)
        # 600 / 3 = 200
        self.assertEqual(self.pass_.cost_per_day, Money(200, "CHF"))

    def test_summer_value_reduces_winter_cost_per_day(self):
        self._summer_activity(Money(50, "CHF"), season_pass=self.pass_)
        self._summer_activity(Money(50, "CHF"), season_pass=self.pass_)

        self.assertEqual(self.pass_.total_summer_value, Money(100, "CHF"))
        self.assertEqual(self.pass_.count_summer_activities(), 2)
        # Average value of summer activities = 100 / 2 = 50
        self.assertEqual(self.pass_.summer_avg_value, Money(50, "CHF"))
        # Winter cost/day = (600 - 100) / 3 = 166.67
        self.assertEqual(self.pass_.cost_per_day, Money(round(500 / 3, 2), "CHF"))

    def test_unattributed_summer_activity_is_ignored(self):
        self._summer_activity(Money(50, "CHF"), season_pass=None)
        self.assertIsNone(self.pass_.total_summer_value)
        self.assertEqual(self.pass_.cost_per_day, Money(200, "CHF"))

    def test_summer_activities_not_counted_as_ski_days(self):
        self._summer_activity(Money(50, "CHF"), season_pass=self.pass_)
        # Ski pipeline / winter day count must remain unaffected.
        self.assertEqual(self.pass_.count_valid_activities(), 3)
        self.assertEqual(Activity.objects.filter(user=self.user).count(), 3)


class SummerActivityViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", email="u@e.com", password="x")
        self.type = SummerActivityType.objects.get(natural_key="hiking")
        self.client.force_login(self.user)

    def test_list_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("summer_activity_list"))
        self.assertEqual(resp.status_code, 302)

    def test_list_and_filter(self):
        SummerActivity.objects.create(
            user=self.user, name="Hike A", activity_type=self.type, date=date(2024, 7, 1),
        )
        resp = self.client.get(reverse("summer_activity_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hike A")
        # Filtering by an unrelated type hides it.
        resp = self.client.get(reverse("summer_activity_list"), {"type": "swimming"})
        self.assertNotContains(resp, "Hike A")

    def test_create(self):
        resp = self.client.post(
            reverse("summer_activity_create"),
            {
                "name": "New hike",
                "activity_type": self.type.id,
                "date": "2024-08-15",
                "distance_km": "12.5",
                "duration_minutes": "90",
            },
        )
        self.assertEqual(resp.status_code, 302)
        sa = SummerActivity.objects.get(name="New hike")
        self.assertEqual(sa.user, self.user)
        self.assertEqual(sa.distance, 12500.0)            # km -> m
        self.assertEqual(sa.duration, timedelta(minutes=90))

    def test_delete(self):
        sa = SummerActivity.objects.create(
            user=self.user, name="Hike", activity_type=self.type, date=date(2024, 7, 1),
        )
        resp = self.client.post(reverse("summer_activity_delete", args=[sa.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SummerActivity.objects.filter(pk=sa.pk).exists())

    def test_cannot_edit_other_users_activity(self):
        other = User.objects.create_user(username="o", email="o@e.com", password="x")
        sa = SummerActivity.objects.create(
            user=other, name="Theirs", activity_type=self.type, date=date(2024, 7, 1),
        )
        resp = self.client.get(reverse("summer_activity_edit", args=[sa.pk]))
        self.assertEqual(resp.status_code, 404)
