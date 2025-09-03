from celery import shared_task
import logging
from .osm_parser import parse_osm_file
import os

logger = logging.getLogger(__name__)

@shared_task
def parse_osm_file_task(osm_file_path, parse_options):
    logger.debug(f'Working directory: {os.getcwd()}')
    try:
        parse_osm_file(osm_file_path, parse_options)
        logger.info(f"Successfully parsed OSM file: {osm_file_path}")
    except Exception as e:
        logger.error(f"Error parsing OSM file {osm_file_path}: {e}")
        raise
