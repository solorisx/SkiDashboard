import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from .models import Activity, LiftRide, PisteRide

logger = logging.getLogger(__name__)


def invalidate_activity_completeness_cache(activity_id):
    """
    Helper function to invalidate all completeness caches for an activity.

    Args:
        activity_id: ID of the activity whose cache should be invalidated
    """
    cache_keys = [
        f"activity_completeness_{activity_id}",
        f"activity_piste_completeness_{activity_id}",
    ]

    for cache_key in cache_keys:
        if cache.delete(cache_key):
            logger.debug(f"Invalidated cache: {cache_key}")


@receiver(post_save, sender=Activity)
def invalidate_activity_cache_on_save(sender, instance, **kwargs):
    """
    Invalidate activity completeness caches when an activity is saved.
    This ensures cached data is refreshed when activities are reprocessed or manually modified.
    """
    invalidate_activity_completeness_cache(instance.id)


@receiver(post_delete, sender=Activity)
def invalidate_activity_cache_on_delete(sender, instance, **kwargs):
    """
    Invalidate activity completeness caches when an activity is deleted.
    """
    invalidate_activity_completeness_cache(instance.id)


@receiver(post_save, sender=LiftRide)
def invalidate_activity_cache_on_lift_ride_save(sender, instance, **kwargs):
    """
    Invalidate activity lift completeness cache when a lift ride is added or modified.
    """
    activity_id = instance.lap.activity_id
    cache_key = f"activity_completeness_{activity_id}"
    if cache.delete(cache_key):
        logger.debug(f"Invalidated cache after lift ride save: {cache_key}")


@receiver(post_delete, sender=LiftRide)
def invalidate_activity_cache_on_lift_ride_delete(sender, instance, **kwargs):
    """
    Invalidate activity lift completeness cache when a lift ride is deleted.
    """
    activity_id = instance.lap.activity_id
    cache_key = f"activity_completeness_{activity_id}"
    if cache.delete(cache_key):
        logger.debug(f"Invalidated cache after lift ride delete: {cache_key}")


@receiver(post_save, sender=PisteRide)
def invalidate_activity_cache_on_piste_ride_save(sender, instance, **kwargs):
    """
    Invalidate activity piste completeness cache when a piste ride is added or modified.
    """
    activity_id = instance.lap.activity_id
    cache_key = f"activity_piste_completeness_{activity_id}"
    if cache.delete(cache_key):
        logger.debug(f"Invalidated cache after piste ride save: {cache_key}")


@receiver(post_delete, sender=PisteRide)
def invalidate_activity_cache_on_piste_ride_delete(sender, instance, **kwargs):
    """
    Invalidate activity piste completeness cache when a piste ride is deleted.
    """
    activity_id = instance.lap.activity_id
    cache_key = f"activity_piste_completeness_{activity_id}"
    if cache.delete(cache_key):
        logger.debug(f"Invalidated cache after piste ride delete: {cache_key}")
