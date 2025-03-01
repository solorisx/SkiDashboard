import os
from django.core.management.base import BaseCommand, CommandError
from osm.osm_parser import parse_osm_file

class Command(BaseCommand):
    help = 'Parses the provided FIT or OSM file'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str)
        parser.add_argument('--ways', action='store_true', help='Parse ways only')
        parser.add_argument('--relations', action='store_true', help='Parse relations only')
        parser.add_argument('--nodes', action='store_true', help='Parse nodes only')
        parser.add_argument('--areas', action='store_true', help='Parse areas only')

    def handle(self, *args, **options):
        file = options['file']
        filename, ext = os.path.splitext(file)
        
        scope = [options['nodes'], options['ways'], options['relations'], options['areas']]

        if ext == '.osm':
            if not any(scope):
                scope = [True, True, True, True]
            parse_osm_file(file, scope)
            self.stdout.write(self.style.SUCCESS('Successfully parsed "%s"' % file))
        else:
            raise CommandError('Not a valid file')