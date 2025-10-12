from celery import shared_task
import logging
import uuid
from datetime import datetime

from osm.osm_downloader import load_osm
from .osm_parser import parse_osm_file, OSMHandler
from .task_manager import get_task_manager, TaskStatus
import os

logger = logging.getLogger(__name__)

@shared_task
def parse_osm_file_task(osm_file_path, parse_options, task_id=None, resume_from=0):
    """
    Cloud-safe OSM file parsing task with automatic checkpointing.

    Args:
        osm_file_path: Path to OSM file
        parse_options: Tuple of (nodes, ways, relations, areas) boolean flags
        task_id: Optional task ID for resuming
        resume_from: Item index to resume from
    """
    if not task_id:
        task_id = f"osm_parse_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    logger.info(f'Starting OSM parsing task {task_id} (resume_from: {resume_from})')
    logger.debug(f'Working directory: {os.getcwd()}')

    task_manager = get_task_manager()

    try:
        load_osm()
        logger.debug("Loaded OSM data")

        # Use cloud-safe parsing with checkpointing
        progress = parse_osm_file_cloud_safe(osm_file_path, parse_options, task_id, resume_from)

        if progress.status == TaskStatus.COMPLETED:
            logger.info(f"Successfully completed OSM parsing task {task_id}")
        elif progress.status == TaskStatus.PENDING:
            logger.info(f"Task {task_id} checkpointed and will continue automatically")
        else:
            logger.warning(f"Task {task_id} ended with status: {progress.status}")

    except Exception as e:
        logger.error(f"Error in OSM parsing task {task_id}: {e}")
        raise

@shared_task
def continue_osm_parsing_task(task_id, resume_from):
    """
    Continue a checkpointed OSM parsing task.

    Args:
        task_id: Task ID to continue
        resume_from: Item index to resume from
    """
    logger.info(f"Continuing OSM parsing task {task_id} from index {resume_from}")

    # This would need the original parameters - in practice, we'd store them
    # For now, this is a placeholder for the continuation mechanism
    # In a real implementation, we'd store the original parameters in the cache
    raise NotImplementedError("Task continuation requires parameter storage implementation")


def parse_osm_file_cloud_safe(file_path, scope, task_id, resume_from=0):
    """
    Cloud-safe version of parse_osm_file with automatic checkpointing.

    Args:
        file_path: Path to OSM file
        scope: Tuple of (nodes, ways, relations, areas) boolean flags
        task_id: Unique task identifier
        resume_from: Item index to resume from

    Returns:
        TaskProgress object with final status
    """
    logger.info(f"Starting cloud-safe parsing of OSM file: {file_path}")
    logger.info(f"Scope: {'parsing' if scope[0] else 'skipping'} nodes, "
               f"{'parsing' if scope[1] else 'skipping'} ways, "
               f"{'parsing' if scope[2] else 'skipping'} relations, "
               f"{'parsing' if scope[3] else 'skipping'} areas")

    task_manager = get_task_manager()

    # Load OSM data into handler
    logger.info(f"Loading OSM file into handler: {file_path}")
    handler = OSMHandler(scope)
    handler.apply_file(file_path, locations=True)

    logger.info(f"OSM file loaded: "
               f"{len(handler.nodes) if handler.nodes else 'N/A'} nodes, "
               f"{len(handler.ways) if handler.ways else 'N/A'} ways, "
               f"{len(handler.relations) if handler.relations else 'N/A'} relations, "
               f"{len(handler.areas) if handler.areas else 'N/A'} areas")

    # Process each type of OSM data with cloud-safe chunking
    if scope[0] and handler.nodes:
        logger.info("Processing nodes with cloud-safe chunking")
        from .osm_parser import process_nodes_chunk

        progress = task_manager.execute_with_checkpoints(
            task_id=f"{task_id}_nodes",
            items=handler.nodes,
            processor_func=process_nodes_chunk,
            resume_from=resume_from if resume_from > 0 else 0
        )

        if progress.status != TaskStatus.COMPLETED:
            return progress

    if scope[1] and handler.ways:
        logger.info("Processing ways with cloud-safe chunking")
        from .osm_parser import process_ways_chunk

        progress = task_manager.execute_with_checkpoints(
            task_id=f"{task_id}_ways",
            items=handler.ways,
            processor_func=process_ways_chunk,
            resume_from=0  # Ways processing doesn't support resume yet
        )

        if progress.status != TaskStatus.COMPLETED:
            return progress

    if scope[2] and handler.relations:
        logger.info("Processing relations with cloud-safe chunking")
        from .osm_parser import process_relations_chunk

        progress = task_manager.execute_with_checkpoints(
            task_id=f"{task_id}_relations",
            items=handler.relations,
            processor_func=process_relations_chunk,
            resume_from=0
        )

        if progress.status != TaskStatus.COMPLETED:
            return progress

    if scope[3] and handler.areas:
        logger.info("Processing areas with cloud-safe chunking")
        from .osm_parser import process_areas_chunk

        progress = task_manager.execute_with_checkpoints(
            task_id=f"{task_id}_areas",
            items=handler.areas,
            processor_func=process_areas_chunk,
            resume_from=0
        )

        if progress.status != TaskStatus.COMPLETED:
            return progress

    # Clean up orphan nodes if ways were processed
    if scope[1]:
        logger.info("Cleaning up orphan nodes")
        from .osm_parser import delete_orphan_nodes_batch
        delete_orphan_nodes_batch()

    logger.info(f"Completed cloud-safe parsing of OSM file: {file_path}")
    return progress
