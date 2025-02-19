from stravalib import Client
from allauth.socialaccount.models import SocialAccount,SocialToken
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from pytz import UTC

def get_access_token(User):
    user = User
    account = SocialAccount.objects.get(user=user, provider='strava')
    if account is None:
        raise ValueError("User does not have a Strava account")
    token = SocialToken.objects.get(account=account)
    app = token.app
    print(app)
    print(app.client_id)
    if token.expires_at < UTC.localize(datetime.now()) + timedelta(minutes=5):
        client = Client()
        refresh_response = client.refresh_access_token(
            client_id=app.client_id,
            client_secret=app.secret,
            refresh_token=token.token_secret
        )
        token.token = refresh_response['access_token']
        token.token_secret = refresh_response['refresh_token']
        token.expires_at = datetime.utcfromtimestamp(refresh_response['expires_at'])
    return token.token

def load_activities(User):
    access_token = get_access_token(User)
    print(access_token)
    client = Client(access_token)
    activities = client.get_activities()
    return activities

def test_strava():
    user = User.objects.get(username='admin')
    activities = load_activities(user)
    count = 0
    for activity in activities:
        print(activity)
        count += 1
        if count > 5:
            break
