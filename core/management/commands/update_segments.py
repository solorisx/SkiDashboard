import os
from django.core.management.base import BaseCommand, CommandError
from osm.osm_segments import update_piste_segments

class Command(BaseCommand):
    help = 'Updates all piste segments, takes about 2 hours'

    def handle(self, *args, **options):
        update_piste_segments()