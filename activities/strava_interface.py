from stravalib import Client
from allauth.socialaccount.models import SocialAccount, SocialToken
from datetime import datetime, timedelta
from pytz import UTC

import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)


def refresh_strava_token(user, token, app):
    """
    Refreshes the Strava access token using the refresh token.
    """
    client = Client()
    try:
        refresh_response = client.refresh_access_token(
            client_id=app.client_id, client_secret=app.secret, refresh_token=token.token_secret
        )
    except Exception as e:
        logger.error(f"Failed to refresh Strava token for {user.username}: {e}", exc_info=True, stack_info=True)
        raise

    # Update token details
    token.token = refresh_response.get("access_token")
    token.token_secret = refresh_response.get("refresh_token")
    token.expires_at = datetime.fromtimestamp(refresh_response.get("expires_at", 0), tz=UTC)
    token.save()

    logger.info("Refreshed Strava token for user %s", user.username)
    return token.token


def get_access_token(user):
    """
    Retrieves the latest valid Strava access token for a given user.
    Refreshes the token if it's expired.
    """
    try:
        account = SocialAccount.objects.select_related("user").get(user=user, provider="strava")
        token = SocialToken.objects.select_related("app").get(account=account)
    except SocialAccount.DoesNotExist:
        raise ValueError(f"User {user.username} does not have a Strava account")
    except SocialToken.DoesNotExist:
        raise ValueError(f"No Strava token found for user {user.username}")

    app = token.app

    # Refresh token if it's close to expiring
    if token.expires_at < UTC.localize(datetime.now()) + timedelta(minutes=120):
        return refresh_strava_token(user, token, app)

    return token.token


def deauthorize_strava(user):
    """
    Deauthorizes the Strava token for a given user.
    """
    access_token = get_access_token(user)
    client = Client(access_token)
    response = client.deauthorize()
    logger.info("Deauthorized Strava token for user %s", user.username)
    return response


def load_activities(User, before=None, after=None):
    access_token = get_access_token(User)
    client = Client(access_token)
    activities = client.get_activities(before=before, after=after)
    return activities


def load_activity(User, activity_id):
    access_token = get_access_token(User)
    client = Client(access_token)
    activity = client.get_activity(activity_id)
    return activity


def load_activity_streams(User, activity_id):
    access_token = get_access_token(User)
    client = Client(access_token)
    streams = client.get_activity_streams(
        activity_id,
        types=[
            "time",
            "latlng",
            "distance",
            "altitude",
            "velocity_smooth",
            "heartrate",
            "cadence",
            "watts",
            "temp",
            "moving",
            "grade_smooth",
        ],
    )
    return streams


def load_activity_laps(User, activity_id):
    access_token = get_access_token(User)
    client = Client(access_token)
    laps = client.get_activity_laps(activity_id)
    return laps


class StravaWritePermissionError(Exception):
    """Raised when the Strava token is missing activity:write_permission."""

    pass


def update_activity_description(user, activity_id, description):
    """
    Updates the description of a Strava activity.
    Requires 'activity:write' scope.
    Raises StravaWritePermissionError if the token lacks write permission.
    """
    try:
        access_token = get_access_token(user)
        client = Client(access_token)
        client.update_activity(activity_id, description=description)
        logger.info(f"Updated Strava activity {activity_id} description for user {user.username}")
        return True
    except Exception as e:
        error_str = str(e)
        if "activity:write_permission" in error_str and "missing" in error_str:
            logger.error(f"Failed to update Strava activity {activity_id} description: {e}")
            raise StravaWritePermissionError(error_str)
        logger.error(f"Failed to update Strava activity {activity_id} description: {e}", exc_info=True, stack_info=True)
        return False
