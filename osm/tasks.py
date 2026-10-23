from celery import shared_task
import logging

from osm.osm_downloader import load_osm
from .osm_parser import parse_osm_file, create_stations_from_way_endpoints
from .models import Aerialway, Piste
import os

logger = logging.getLogger(__name__)


@shared_task
def parse_osm_file_task(osm_file_path, parse_options):
    logger.debug(f"Working directory: {os.getcwd()}")
    try:
        load_osm()
        logger.debug("Loaded OSM data")
        parse_osm_file(osm_file_path, parse_options)
        logger.info(f"Successfully parsed OSM file: {osm_file_path}")
    except Exception as e:
        logger.error(f"Error parsing OSM file {osm_file_path}: {e}")
        raise


@shared_task
def update_piste_geometry_task(ski_area_id=None):
    """
    Update geometry for pistes that don't have it.

    Args:
        ski_area_id: Optional ski area ID to filter pistes. If None, updates all pistes.

    Returns:
        dict: Summary of the update process
    """
    logger.info(f"Starting piste geometry update task (ski_area_id={ski_area_id})")

    # Query pistes without geometry
    pistes_query = Piste.objects.filter(geom__isnull=True)

    if ski_area_id:
        # Filter by ski area if provided
        pistes_query = pistes_query.filter(way__skiarea__id=ski_area_id)

    pistes_to_update = list(pistes_query.select_related("way"))
    total_pistes = len(pistes_to_update)

    logger.info(f"Found {total_pistes} pistes without geometry")

    updated_count = 0
    failed_count = 0
    skipped_count = 0

    for piste in pistes_to_update:
        try:
            geom = piste.update_geometry()
            if geom:
                updated_count += 1
                logger.debug(f"Updated geometry for piste {piste.id} ({piste.name or 'unnamed'})")
            else:
                skipped_count += 1
                logger.warning(f"Skipped piste {piste.id} - insufficient nodes")
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to update geometry for piste {piste.id}: {e}")

    summary = {"total": total_pistes, "updated": updated_count, "skipped": skipped_count, "failed": failed_count}

    logger.info(f"Piste geometry update completed: {summary}")
    return summary


@shared_task
def create_aerialway_stations_task():
    """
    Create endpoint stations for every aerialway that currently has no station nodes.

    For each qualifying aerialway the first and last nodes of its associated way
    are promoted to Station objects (bottom and top respectively) using
    create_stations_from_way_endpoints().

    Returns:
        dict: Summary containing 'total', 'created', and 'failed' counts.
    """
    from django.utils import timezone

    logger.info("Starting create_aerialway_stations_task")

    aerialways = Aerialway.objects.filter(station_nodes__isnull=True).select_related("way").distinct()
    total = aerialways.count()
    logger.info(f"Found {total} aerialways without station nodes")

    created_count = 0
    failed_count = 0
    verification_time = timezone.now()

    for aerialway in aerialways:
        try:
            stations = create_stations_from_way_endpoints(aerialway, aerialway.way, verification_time)
            if stations:
                created_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to create stations for aerialway {aerialway.id} " f"(way {aerialway.way_id}): {e}")

    summary = {"total": total, "created": created_count, "failed": failed_count}
    logger.info(f"create_aerialway_stations_task completed: {summary}")
    return summary
