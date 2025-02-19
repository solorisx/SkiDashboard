from django.contrib.auth.models import User
from datetime import datetime, timedelta
from .strava_interface import load_activities
from .activity_parser import parse_strava_activity
from SkiingDashboardApp.activity_models import Activity

def test_strava():
    user = User.objects.get(username='admin')
    activities = load_activities(user, after=datetime.now() - timedelta(days=90))
    for activity in activities:
        print(activity.type)
        if activity.type == 'AlpineSki':
            activity_id = activity.id
            parse_strava_activity(user, activity_id, update=True)
            print(activity_id)
