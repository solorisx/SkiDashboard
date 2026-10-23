from django.core.management.base import BaseCommand
from osm.models import PisteSegment, SkiArea, Piste, SkiAreaBoundary, Node, Way, WayNode, SkiAreaNetwork, Station
from activities.models import Activity
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Updates all piste segments, takes about 2 hours'

    def handle(self, *args, **options):
        # activities
        Activity.objects.all().delete()

        # osm
        Way.objects.all().delete()
        Node.objects.all().delete()
        WayNode.objects.all().delete()
        Piste.objects.all().delete()
        PisteSegment.objects.all().delete()
        Station.objects.all().delete()

        SkiAreaNetwork.objects.all().delete()
        SkiArea.objects.all().delete()
        SkiAreaBoundary.objects.all().delete()


