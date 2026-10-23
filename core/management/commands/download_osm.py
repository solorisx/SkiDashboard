from osm.osm_downloader import load_osm
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Downloads and extracts the OSM file"

    def handle(self, *args, **options):
        load_osm()
