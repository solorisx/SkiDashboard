import os
from django.core.management.base import BaseCommand, CommandError
from SkiingDashboard.core.activity_parser import parse_fit_file
from SkiingDashboard.core.osm_parser import parse_osm_file

class Command(BaseCommand):
    help = 'Parses the provided FIT or OSM file'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str)

    def handle(self, *args, **options):
        file = options['file']
        filename, ext = os.path.splitext(file)
        
        if ext == '.fit':
            parse_fit_file(file)
            self.stdout.write(self.style.SUCCESS('Successfully parsed "%s"' % file))
        elif ext == '.osm':
            parse_osm_file(file)
            self.stdout.write(self.style.SUCCESS('Successfully parsed "%s"' % file))
        else:
            raise CommandError('Not a valid file')