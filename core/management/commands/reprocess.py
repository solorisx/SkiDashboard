import os
from django.core.management.base import BaseCommand, CommandError
from osm.osm_segments import update_piste_segments
from activities.activity_parser import parse_strava_activities
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Reprocess all activities of a user'

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int)

    def handle(self, *args, **options):
        user = User.objects.get(pk=options['user_id'])
        logger.info(f"Reprocessing activities for user {user.username}")
        parse_strava_activities(user=user, all=True, update=True)
        logger.info(f"Reprocessed activities for user {user.username}")