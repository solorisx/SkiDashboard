# tasks.py
from celery import shared_task
from django.contrib.auth import get_user_model
from .activity_parser import sync_strava_activity

User = get_user_model()

@shared_task(rate_limit='20/m')
def sync_strava_activity_task(user_id, activity_id, update=False):
    try:
        user = User.objects.get(id=user_id)
        sync_strava_activity(user, activity_id, update=update)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to sync Strava activity in task: {e}")
