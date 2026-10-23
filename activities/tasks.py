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

@shared_task(rate_limit='10/m')
def sync_strava_activity_task(user_id, activity_id, update=False):
    try:
        user = User.objects.get(id=user_id)
        sync_strava_activity(user, activity_id, update=update)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to sync Strava activity in task: {e}", exc_info=True, stack_info=True)
        raise

@shared_task(rate_limit='10/m')
def delete_strava_activity_task(user_id, activity_id):
    """Delete a user's activity after confirming with Strava that it no longer exists."""
    from stravalib.exc import ObjectNotFound

    user = User.objects.get(id=user_id)
    try:
        load_activity(user, activity_id)
    except ObjectNotFound:
        deleted, _ = Activity.objects.filter(user=user, strava_id=activity_id).delete()
        logger.info(f"Deleted activity {activity_id} of user {user.username} as per Strava webhook ({deleted} rows).")
        return
    logger.warning(f"Ignoring delete webhook for activity {activity_id}: it still exists on Strava.")

@shared_task
def sync_user_activities_task(user_id, all=False, update=False):
    parse_strava_activities_task.delay(user_id, all=all, update=update)

@shared_task
def parse_strava_activities_task(user_id, all=False, update=False):
    from django.conf import settings as django_settings
    user = User.objects.get(id=user_id)
    profile = UserProfile.objects.get(user=user)
    if all:
        if profile.is_premium_active():
            after = None
        else:
            max_days = getattr(django_settings, 'FREE_TIER_MAX_SYNC_DAYS', 365)
            after = datetime.now() - timedelta(days=max_days)
    else:
        if profile.last_strava_sync:
            after = profile.last_strava_sync
        else:
            after = datetime.now() - timedelta(days=90)
    
    activities = load_activities(user, after=after)

    for activity in activities:
        if activity.type == 'AlpineSki':
            try:
                activity_id = activity.id
                if update and Activity.objects.filter(user=user, strava_id=activity_id).exists():
                    activity_obj = Activity.objects.get(user=user, strava_id=activity_id)
                    if activity_obj.manually_modified:
                        if all:
                            logger.info(f"Skipping update of manually modified activity {activity_id} for user {user}")
                            continue
                        else:
                            logger.info(f"Updating manually modified activity {activity_id} for user {user} due to per activity sync")
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
def recalculate_completeness_task(user_id=None, skiarea_id=None):
    from .utils.completeness import calculate_ski_area_completeness
    from .utils.seasons import get_seasons
    from osm.models import SkiArea
    user = User.objects.get(id=user_id) if user_id else None
    skiareas = Activity.objects.filter(user=user).values_list('ski_area', flat=True).distinct() if not skiarea_id else [skiarea_id]
    for skiarea in skiareas:
        skiarea = SkiArea.objects.get(id=skiarea)
        logger.info(f"Recalculating completeness for ski area {skiarea} and user {user}")
        result = calculate_ski_area_completeness(user, skiarea, force_calc=True)
        for season in get_seasons(user=user):
            result = calculate_ski_area_completeness(user, skiarea, season=season, force_calc=True)
        logger.info(f"Recalculated completeness for {'user ' + str(user) if user else 'all users'}. Result: {result}")
