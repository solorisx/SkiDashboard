from datetime import datetime
import logging
from django.contrib.contenttypes.models import ContentType
from djmoney.models.fields import MoneyField
from osm.models import SkiArea, SkiAreaBoundary, SkiAreaNetwork, SkiAreaNetworkMember

logger = logging.getLogger('SkiingDashboard')

def init_networks(request):
    """
    Creates SkiAreaNetwork instances for each SkiArea.
    """
    
    if not request.user.is_staff:
        logger.error("Unauthorized attempt to initialize ski area networks.")
        return
    

    topcard, created = SkiAreaNetwork.objects.get_or_create(name="Topcard", season_pass_price=1300)
    if not created:
        logger.warning("Topcard network already exists, resetting members.")
        topcard.members.all().delete()

    # TODO: use json to load ski areas
    
    topcard_areas = ["Laax", "Arosa Lenzerheide", "Davos Klosters", "Parsenn", "Jakobshorn", "Rinerhorn", "Madrisa"]
    topcard_addon = ["Titlis", "Adelboden-Lenk", "Jungfrau Ski Region", "Aletsch Arena"]

    for area in topcard_areas:
        try:
            skiareas = SkiArea.objects.filter(name__icontains=area)
            for skiarea in skiareas:
                member, _ = SkiAreaNetworkMember.objects.get_or_create(
                    member=skiarea,
                    ski_area_network=topcard,
                    defaults={
                        'valid_during': 'winter',
                        'valid_from': datetime(2024, 11, 1),
                        'max_days': 365,
                    }
                )
                logger.info(f"Added {area} to Topcard network.")
        except SkiArea.DoesNotExist:
            logger.warning(f"Could not find ski area {area}")

    for area in topcard_addon:
        try:
            skiareas = SkiArea.objects.filter(name__icontains=area)
            for skiarea in skiareas:
                member, _ = SkiAreaNetworkMember.objects.get_or_create(
                    ski_area_network=topcard,
                    member=skiarea,
                    defaults={
                        'valid_during': 'winter',
                        'valid_from': datetime(2025, 11, 1),
                        'max_days': 4,
                    }
                )
                logger.info(f"Added {area} to Topcard network add-on. ({skiarea.name})")
        except SkiArea.DoesNotExist:
            logger.warning(f"Could not find ski area {area}")

           


    # TODO: add Tirol Snow Card with tsc_areas.json
    



    logger.info("Ski area networks initialized.")