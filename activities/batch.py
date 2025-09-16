import logging
from datetime import timedelta, datetime

from core.models import UserProfile
from .strava_interface import load_activities

from .tasks import sync_strava_activity_task

logger = logging.getLogger(__name__)

def parse_strava_activities(user, all=False, update=False):
    # deprecated, use parse_strava_activities_task instead
    if all:
        max_strava_sync = UserProfile.objects.get(user=user).max_strava_sync
        if max_strava_sync == -1:
            after = None
        else:
            after = datetime.now() - timedelta(days=max_strava_sync)
    else:
        after = datetime.now() - timedelta(days=90)
    
    activities = load_activities(user, after=after)

    for activity in activities:
        if activity.type == 'AlpineSki':
            try:
                activity_id = activity.id
                sync_strava_activity_task.delay(user.id, activity_id, update)
            except Exception as e:
                logger.error(f"Failed to queue task for Strava activity {activity_id}: {e}", exc_info=True, stack_info=True)
                continue


def parse_strava_activity(user, activity_id, update=False, background=True):
    if background:
        sync_strava_activity_task.delay(user.id, activity_id, update)
    else:
        sync_strava_activity_task(user.id, activity_id, update)