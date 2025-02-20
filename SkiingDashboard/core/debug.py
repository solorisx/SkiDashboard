from django.contrib.auth.models import User
from datetime import datetime, timedelta
from .strava_interface import load_activities
from .activity_parser import parse_strava_activity
from SkiingDashboardApp.activity_models import Activity, Lap, Aerialway, LiftRide

def test_strava():
    user = User.objects.get(username='admin')
    activities = load_activities(user, after=datetime.now() - timedelta(days=90))
    #Activity.objects.filter(user=user).delete()
    for activity in activities:
        if activity.type == 'AlpineSki':
            activity_id = activity.id
            parse_strava_activity(user, activity_id, update=True)


def print_activities():
    user = User.objects.get(username='admin')
    for activity in Activity.objects.filter(user=user):
        name = activity.name if activity.name else "Unnamed activity"
        print(f"Activity {activity.strava_id} {name}")
        print(activity.ski_area.name if activity.ski_area else "Unknown ski area")
        laps = Lap.objects.filter(activity=activity)
        for lap in laps:
            print(f"Lap {lap.lap_index}: {lap.total_distance} m")
            for lift_ride in lap.lift_rides.all():
                print(f"  Lift: {lift_ride.name}")

def test_strava_activity(activity_id):
    user = User.objects.get(username='admin')
    parse_strava_activity(user, activity_id, update=True)