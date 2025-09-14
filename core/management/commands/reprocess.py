import os
from django.core.management.base import BaseCommand, CommandError
from activities.models import Activity
from osm.osm_segments import update_piste_segments
from activities.activity_parser import calc_ridden_segments
from activities.batch import parse_strava_activities
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Reprocess all activities of a user'

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int)
        parser.add_argument('--segments', action='store_true', help='Only reprocess segments')

    def handle(self, *args, **options):
        user = User.objects.get(pk=options['user_id'])

        if options['segments']:
            logger.info(f"Reprocessing segments for user {user.username}")
            activities = Activity.objects.filter(user=user)
            for activity in activities:
                calc_ridden_segments(activity)
                logger.info(f"Reprocessed segments for activity {activity.id} - {activity.strava_id} for user {user.username}")
        else:
            logger.info(f"Reprocessing activities for user {user.username}")
            parse_strava_activities(user=user, all=True, update=True)
            logger.info(f"Reprocessed activities for user {user.username}")