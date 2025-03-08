import os
from django.core.management.base import BaseCommand, CommandError
from osm.osm_segments import update_piste_segments
from osm.models import PisteSegment
from activities.models import ActivityPisteSegment
from activities.activity_parser import parse_strava_activity
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Updates all piste segments, takes about 2 hours'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Reset all piste segments')

    def handle(self, *args, **options):
        if options['reset']:
            logger.info(f"Deleting all piste segments ({PisteSegment.objects.count()})")
            activities = ActivityPisteSegment.objects.all().values("activity").distinct()
            logger.info(f"Affected activities: {len(activities)}")
            ActivityPisteSegment.objects.all().delete()
            PisteSegment.objects.all().delete()

        logger.debug("Updating all piste segments")
        update_piste_segments()

        for activity in activities:
            parse_strava_activity(user=activity.user, activity_id=activity.strava_id, update=True)
            logger.info(f"Reprocessed activity {activity.strava_id} due to reset of piste segments")

        logger.info(f"Updated all piste segments ({PisteSegment.objects.count()})")