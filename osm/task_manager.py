"""
Cloud-safe task management for OSM parsing operations.

This module provides utilities to split large OSM parsing tasks into smaller,
manageable chunks that can be executed in cloud environments without hitting
memory limits or timeouts that cause SIGKILL.
"""

import logging
import time
from django.core.cache import cache

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("psutil not available - memory monitoring will be disabled")
from django.utils import timezone
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskProgress:
    """Track progress of a parsing task."""
    task_id: str
    status: TaskStatus
    total_items: int
    processed_items: int
    start_time: float
    last_update: float
    error_message: Optional[str] = None
    current_chunk: int = 0
    total_chunks: int = 0

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_items == 0:
            return 100.0
        return (self.processed_items / self.total_items) * 100.0

    @property
    def elapsed_time(self) -> float:
        """Calculate elapsed time in seconds."""
        return time.time() - self.start_time

    @property
    def estimated_remaining_time(self) -> Optional[float]:
        """Estimate remaining time based on current progress."""
        if self.processed_items == 0:
            return None

        rate = self.processed_items / self.elapsed_time
        remaining_items = self.total_items - self.processed_items
        return remaining_items / rate if rate > 0 else None


class CloudTaskManager:
    """
    Manages cloud-safe execution of OSM parsing tasks.

    Key features:
    - Memory monitoring with automatic chunk size adjustment
    - Progress tracking with resumable checkpoints
    - Timeout handling with graceful task subdivision
    - Resource usage monitoring
    """

    def __init__(self,
                 max_memory_mb: int = 512,
                 max_execution_time: int = 300,  # 5 minutes
                 initial_chunk_size: int = 1000,
                 min_chunk_size: int = 100):
        """
        Initialize task manager with cloud-safe defaults.

        Args:
            max_memory_mb: Maximum memory usage before triggering subdivision
            max_execution_time: Maximum execution time before checkpointing
            initial_chunk_size: Starting chunk size for processing
            min_chunk_size: Minimum chunk size (prevents infinite subdivision)
        """
        self.max_memory_mb = max_memory_mb
        self.max_execution_time = max_execution_time
        self.initial_chunk_size = initial_chunk_size
        self.min_chunk_size = min_chunk_size

    def get_current_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        if not PSUTIL_AVAILABLE:
            return 0.0  # Fallback when psutil is not available

        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0  # Fallback on any psutil error

    def should_checkpoint(self, start_time: float) -> bool:
        """
        Determine if task should checkpoint based on time and memory.

        Args:
            start_time: Task start timestamp

        Returns:
            True if task should checkpoint and restart
        """
        elapsed_time = time.time() - start_time
        memory_usage = self.get_current_memory_usage()

        time_exceeded = elapsed_time > self.max_execution_time
        memory_exceeded = memory_usage > self.max_memory_mb

        if time_exceeded:
            logger.warning(f"Time limit exceeded: {elapsed_time:.1f}s > {self.max_execution_time}s")
        if memory_exceeded:
            logger.warning(f"Memory limit exceeded: {memory_usage:.1f}MB > {self.max_memory_mb}MB")

        return time_exceeded or memory_exceeded

    def calculate_adaptive_chunk_size(self,
                                    current_chunk_size: int,
                                    processing_time: float,
                                    memory_usage: float) -> int:
        """
        Calculate adaptive chunk size based on performance metrics.

        Args:
            current_chunk_size: Current chunk size
            processing_time: Time taken to process current chunk
            memory_usage: Memory used during processing

        Returns:
            Adjusted chunk size
        """
        # If memory usage is high, reduce chunk size
        if memory_usage > self.max_memory_mb * 0.8:
            new_size = max(self.min_chunk_size, int(current_chunk_size * 0.7))
            logger.info(f"Reducing chunk size due to memory usage: {current_chunk_size} -> {new_size}")
            return new_size

        # If processing is fast and memory usage is low, increase chunk size
        if processing_time < 10 and memory_usage < self.max_memory_mb * 0.5:
            new_size = min(current_chunk_size * 2, self.initial_chunk_size * 2)
            logger.info(f"Increasing chunk size due to good performance: {current_chunk_size} -> {new_size}")
            return new_size

        return current_chunk_size

    def save_progress(self, progress: TaskProgress):
        """Save task progress to cache for resumability."""
        cache_key = f"osm_task_progress_{progress.task_id}"
        cache.set(cache_key, progress, timeout=3600 * 24)  # 24 hours
        logger.debug(f"Saved progress for task {progress.task_id}: {progress.progress_percentage:.1f}%")

    def load_progress(self, task_id: str) -> Optional[TaskProgress]:
        """Load task progress from cache."""
        cache_key = f"osm_task_progress_{task_id}"
        progress = cache.get(cache_key)
        if progress:
            logger.info(f"Resumed task {task_id} at {progress.progress_percentage:.1f}%")
        return progress

    def create_chunks(self, items: List[Any], chunk_size: int) -> List[List[Any]]:
        """Create chunks from items list."""
        chunks = []
        for i in range(0, len(items), chunk_size):
            chunks.append(items[i:i + chunk_size])
        return chunks

    def execute_with_checkpoints(self,
                               task_id: str,
                               items: List[Any],
                               processor_func,
                               resume_from: int = 0) -> TaskProgress:
        """
        Execute a task with cloud-safe checkpointing.

        Args:
            task_id: Unique task identifier
            items: List of items to process
            processor_func: Function to process each chunk
            resume_from: Item index to resume from

        Returns:
            Final task progress
        """
        start_time = time.time()

        # Try to load existing progress
        progress = self.load_progress(task_id)
        if not progress:
            progress = TaskProgress(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                total_items=len(items),
                processed_items=resume_from,
                start_time=start_time,
                last_update=start_time
            )
        else:
            progress.status = TaskStatus.RUNNING
            progress.last_update = time.time()

        # Start from resume point
        remaining_items = items[resume_from:]
        chunk_size = self.initial_chunk_size

        try:
            chunks = self.create_chunks(remaining_items, chunk_size)
            progress.total_chunks = len(chunks)

            for chunk_idx, chunk in enumerate(chunks):
                chunk_start_time = time.time()
                memory_before = self.get_current_memory_usage()

                # Check if we should checkpoint before processing
                if self.should_checkpoint(start_time):
                    logger.info(f"Checkpointing task {task_id} at chunk {chunk_idx}")
                    progress.status = TaskStatus.PENDING
                    self.save_progress(progress)

                    # Schedule continuation as new task
                    from .tasks import continue_osm_parsing_task
                    continue_osm_parsing_task.delay(
                        task_id,
                        resume_from + progress.processed_items - resume_from
                    )
                    return progress

                # Process chunk
                try:
                    result = processor_func(chunk)
                    progress.processed_items += len(chunk)
                    progress.current_chunk = chunk_idx + 1

                except Exception as e:
                    logger.error(f"Error processing chunk {chunk_idx} of task {task_id}: {e}")
                    progress.status = TaskStatus.FAILED
                    progress.error_message = str(e)
                    self.save_progress(progress)
                    raise

                # Update metrics and adaptive chunk size
                chunk_time = time.time() - chunk_start_time
                memory_after = self.get_current_memory_usage()
                chunk_size = self.calculate_adaptive_chunk_size(
                    chunk_size, chunk_time, memory_after
                )

                # Save progress periodically
                if chunk_idx % 10 == 0:
                    progress.last_update = time.time()
                    self.save_progress(progress)
                    logger.info(f"Task {task_id} progress: {progress.progress_percentage:.1f}% "
                              f"(chunk {chunk_idx + 1}/{len(chunks)})")

            # Task completed successfully
            progress.status = TaskStatus.COMPLETED
            progress.last_update = time.time()
            self.save_progress(progress)
            logger.info(f"Task {task_id} completed successfully in {progress.elapsed_time:.1f}s")

        except Exception as e:
            progress.status = TaskStatus.FAILED
            progress.error_message = str(e)
            progress.last_update = time.time()
            self.save_progress(progress)
            logger.error(f"Task {task_id} failed: {e}")
            raise

        return progress


def get_task_manager() -> CloudTaskManager:
    """Get a configured task manager instance."""
    return CloudTaskManager(
        max_memory_mb=512,      # Conservative for cloud environments
        max_execution_time=240, # 4 minutes (leave buffer for cleanup)
        initial_chunk_size=500, # Smaller initial chunks for safety
        min_chunk_size=50       # Minimum viable chunk size
    )