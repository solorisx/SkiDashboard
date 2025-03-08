import os
from django.core.management.base import BaseCommand, CommandError
from osm.osm_segments import update_piste_segments
from osm.models import PisteSegment, SkiArea, Piste
from activities.models import ActivityPisteSegment
from activities.activity_parser import parse_strava_activity, calc_ridden_segments
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Updates all piste segments, takes about 2 hours'

    def add_arguments(self, parser):
        parser.add_argument('osm_id', type=int, nargs='?', help='OSM ID of the piste to update')
        parser.add_argument('--reset', action='store_true', help='Reset all piste segments')

    def handle(self, *args, **options):
        osm_id = options['osm_id']
        area = SkiArea.objects.get(osm_id=osm_id)
        if not area:
            raise ValueError(f"Area with OSM ID {osm_id} not found")
        pistes = Piste.objects.filter(geom__coveredby=area.geom)
        if options['reset']:
            segments = PisteSegment.objects.filter(piste__in=pistes)
            logger.info(f"Deleting all piste segments ({segments.count()})")
            activity_segments = ActivityPisteSegment.objects.filter(piste_segment__in=segments)
            activities = activity_segments.values("activity").distinct()
            logger.info(f"Affected activities: {len(activities)}")
            activity_segments.delete()
            segments.delete()

        logger.debug("Updating all piste segments")
        for piste in pistes:
            update_piste_segments(piste.way.osm_id, force=True)

        logger.debug("Updated segments. Recalculating ridden segments")
        for activity in activities:
            calc_ridden_segments(activity)
            logger.info(f"Reprocessed activity {activity.strava_id} due to reset of piste segments")

        logger.info(f"Updated all piste segments ({PisteSegment.objects.filter(piste__in=pistes).count()})")