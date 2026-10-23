from django.core.management.base import BaseCommand
from osm.osm_segments import update_piste_segments
from osm.models import PisteSegment
from activities.models import Activity, ActivityPisteSegment
from activities.activity_parser import calc_ridden_segments
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Updates all piste segments, takes about 2 hours"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Reset all piste segments")

    def handle(self, *args, **options):
        activities = []
        if options["reset"]:
            logger.info(f"Deleting all piste segments ({PisteSegment.objects.count()})")
            # Evaluate before the segments are deleted, so the affected activities can be reprocessed afterwards
            activity_ids = ActivityPisteSegment.objects.values_list("activity", flat=True).distinct()
            activities = list(Activity.objects.filter(id__in=activity_ids))
            logger.info(f"Affected activities: {len(activities)}")
            ActivityPisteSegment.objects.all().delete()
            PisteSegment.objects.all().delete()

        logger.debug("Updating all piste segments")
        update_piste_segments()

        # Only segment assignments were invalidated, so rebuild those rather than re-importing from Strava,
        # which would overwrite manually modified activities
        for activity in activities:
            calc_ridden_segments(activity)
            logger.info(f"Recalculated piste segments for activity {activity.strava_id} after segment reset")

        logger.info(f"Updated all piste segments ({PisteSegment.objects.count()})")
