from stravalib import Client
from allauth.socialaccount.models import SocialAccount,SocialToken
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from pytz import UTC

from SkiingDashboardApp.osm_models import Way, Node, Aerialway, Piste, SkiArea
from django.db import transaction
from django.db.models import Q
import logging

# Get an instance of a logger
logger = logging.getLogger('SkiingDashboard')



def get_access_token(User):
    user = User
    account = SocialAccount.objects.get(user=user, provider='strava')
    if account is None:
        raise ValueError("User does not have a Strava account")
    token = SocialToken.objects.get(account=account)
    app = token.app
    print(app)
    print(app.client_id)
    if True: #token.expires_at < UTC.localize(datetime.now()) + timedelta(minutes=5):
        client = Client()
        refresh_response = client.refresh_access_token(
            client_id=app.client_id,
            client_secret=app.secret,
            refresh_token=token.token_secret
        )
        token.token = refresh_response['access_token']
        token.token_secret = refresh_response['refresh_token']
        token.expires_at = datetime.fromtimestamp(refresh_response['expires_at'])
        logger.info("Refreshed Strava token for user %s", user.username)
    return token.token

def load_activities(User, after=None):
    access_token = get_access_token(User)
    print(access_token)
    client = Client(access_token)
    activities = client.get_activities(after=after)
    return activities

def load_activity(User, activity_id):
    access_token = get_access_token(User)
    client = Client(access_token)
    activity = client.get_activity(activity_id)
    return activity

def load_activity_streams(User, activity_id):
    access_token = get_access_token(User)
    client = Client(access_token)
    streams = client.get_activity_streams(activity_id, types=['time', 'latlng', 'distance', 'altitude', 'velocity_smooth', 'heartrate', 'cadence', 'watts', 'temp', 'moving', 'grade_smooth'])
    return streams

def load_activity_laps(User, activity_id):
    access_token = get_access_token(User)
    client = Client(access_token)
    laps = client.get_activity_laps(activity_id)
    return laps

def test_strava():
    user = User.objects.get(username='admin')
    activities = load_activities(user, after=datetime.now() - timedelta(days=90))
    for activity in activities:
        print(activity.type)
        if activity.type == 'AlpineSki':
            streams = load_activity_streams(user, activity.id)
            print(streams)
            break