from datetime import datetime
import logging
from django.contrib.contenttypes.models import ContentType
from djmoney.models.fields import MoneyField
from SkiingDashboardApp.models import SkiArea, SkiAreaBoundary, SkiAreaNetwork, SkiAreaNetworkMember

logger = logging.getLogger('SkiingDashboard')

def init_networks(request):
    """
    Creates SkiAreaNetwork instances for each SkiArea.
    """
    
    if not request.user.is_staff:
        logger.error("Unauthorized attempt to initialize ski area networks.")
        return
    

    topcard, _ = SkiAreaNetwork.objects.get_or_create(name="Topcard", season_pass_price=1300)
    topcard_areas = ["Laax", "Arosa Lenzerheide", "Davos Klosters", "Parsenn", "Jakobshorn", "Rinerhorn", "Madrisa"]
    topcard_addon = ["Titlis", "Adelboden-Lenk", "Jungfrau Ski Region", "Aletsch Arena"]

    for area in topcard_areas:
        try:
            skiarea = SkiArea.objects.get(name__icontains=area)
            member, _ = SkiAreaNetworkMember.objects.get_or_create(
                ski_area_network=topcard,
                content_type=ContentType.objects.get_for_model(skiarea),
                object_id=skiarea.id,
                defaults={
                    'valid_during': 'winter',
                    'valid_from': datetime(2025, 11, 1),
                    'max_days': 365,
                }
            )
            logger.info(f"Added {area} to Topcard network.")
        except SkiArea.DoesNotExist:
            logger.warning(f"Could not find ski area {area}")

        try:
            skiarea_boundary = SkiAreaBoundary.objects.get(name__icontains=area)
            member, _ = SkiAreaNetworkMember.objects.get_or_create(
                ski_area_network=topcard,
                content_type=ContentType.objects.get_for_model(skiarea_boundary),
                object_id=skiarea_boundary.id,
                defaults={
                    'valid_during': 'winter',
                    'valid_from': datetime(2025, 11, 1),
                    'max_days': 365,
                }
            )
            logger.info(f"Added {area} boundary to Topcard network.")
        except SkiAreaBoundary.DoesNotExist:
            logger.warning(f"Could not find ski area boundary {area}")

    for area in topcard_addon:
        try:
            skiarea = SkiArea.objects.get(name__icontains=area)
            member, _ = SkiAreaNetworkMember.objects.get_or_create(
                ski_area_network=topcard,
                content_type=ContentType.objects.get_for_model(skiarea),
                object_id=skiarea.id,
                defaults={
                    'valid_during': 'winter',
                    'valid_from': datetime(2025, 11, 1),
                    'max_days': 4,
                }
            )
            logger.info(f"Added {area} to Topcard network add-on. ({skiarea.name})")
        except SkiArea.DoesNotExist:
            logger.warning(f"Could not find ski area {area}")

        try:
            skiarea_boundary = SkiAreaBoundary.objects.get(name__icontains=area)
            member, _ = SkiAreaNetworkMember.objects.get_or_create(
                ski_area_network=topcard,
                content_type=ContentType.objects.get_for_model(skiarea_boundary),
                object_id=skiarea_boundary.id,
                defaults={
                    'valid_during': 'winter',
                    'valid_from': datetime(2025, 11, 1),
                    'max_days': 4,
                }
            )
            logger.info(f"Added {area} boundary to Topcard network add-on. ({skiarea_boundary.name})")
        except SkiAreaBoundary.DoesNotExist:
            logger.warning(f"Could not find ski area boundary {area}")        


    # TODO: Add Tirol Snowcard areas

    logger.info("Ski area networks initialized.")