# tasks.py
from celery import shared_task
from django.contrib.auth import get_user_model
from .activity_parser import sync_strava_activity
from .models import Activity, StravaSyncSettings
import logging
from datetime import timedelta, datetime
from allauth.socialaccount.models import SocialAccount

from core.models import UserProfile
from .strava_interface import load_activities, load_activity, load_activity_streams, load_activity_laps

User = get_user_model()
logger = logging.getLogger(__name__)

def iter_strava_users():
    """
    Return all users who have an active Strava SocialAccount.
    Provider name is 'strava' (per django-allauth setup).
    """
    strava_accounts = SocialAccount.objects.filter(provider="strava")
    user_ids = strava_accounts.values_list("user_id", flat=True)
    return User.objects.filter(id__in=user_ids)

def run_scheduled_strava_sync(manual=False):
    settings_row = StravaSyncSettings.objects.first()
    if not manual and (not settings_row or not settings_row.enable_scheduled_sync):
        return "Scheduled sync disabled."

    for user in iter_strava_users():
        sync_user_activities_task.delay(user.id)
    return "Triggered per-user sync."

@shared_task(rate_limit='20/m')
def sync_strava_activity_task(user_id, activity_id, update=False):
    try:
        user = User.objects.get(id=user_id)
        sync_strava_activity(user, activity_id, update=update)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to sync Strava activity in task: {e}", exc_info=True, stack_info=True)
        raise

@shared_task
def sync_user_activities_task(user_id, all=False, update=False):
    parse_strava_activities_task.delay(user_id, all=all, update=update)

@shared_task
def parse_strava_activities_task(user_id, all=False, update=False):
    user = User.objects.get(id=user_id)
    if all:
        max_strava_sync = UserProfile.objects.get(user=user).max_strava_sync
        if max_strava_sync == -1:
            after = None
        else:
            after = datetime.now() - timedelta(days=max_strava_sync)
    else:
        if UserProfile.objects.get(user=user).last_strava_sync:
            after = UserProfile.objects.get(user=user).last_strava_sync
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

    UserProfile.objects.filter(user=user).update(last_strava_sync=datetime.now())

@shared_task
def scheduled_strava_sync(manual=False):
    """
    Sweep all Strava-connected users for new activities.
    Honours the enable_scheduled_sync toggle.
    """
    return run_scheduled_strava_sync(manual)

@shared_task
def reassign_badges_task(user_id):
    from .badges import reassign_all_badges
    user = User.objects.get(id=user_id) if user_id else None
    result = reassign_all_badges(user)
    logger.info(f"Reassigned badges for {'user ' + str(user) if user else 'all users'}. Result: {result}")

@shared_task
def recalculate_completeness_task(user_id=None):
    from .utils.completeness import calculate_ski_area_completeness
    from .utils.seasons import get_seasons
    from osm.models import SkiArea
    user = User.objects.get(id=user_id) if user_id else None
    for skiarea in Activity.objects.filter(user=user).values_list('ski_area', flat=True).distinct():
        skiarea = SkiArea.objects.get(id=skiarea)
        logger.info(f"Recalculating completeness for ski area {skiarea} and user {user}")
        result = calculate_ski_area_completeness(user, skiarea, force_calc=True)
        for season in get_seasons(user=user):
            result = calculate_ski_area_completeness(user, skiarea, season=season, force_calc=True)
        logger.info(f"Recalculated completeness for {'user ' + str(user) if user else 'all users'}. Result: {result}")
