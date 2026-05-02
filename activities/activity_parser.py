import heapq
import hashlib
import logging
import time
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import Dict, List, Optional, Tuple, Any
import polyline
from django.utils import timezone
import pytz
import re
from activities.models import Activity, Lap, Record, LiftRide, ActivityPisteSegment, PisteRide
from osm.models import Node, Way, Aerialway, SkiArea, Station, SkiAreaBoundary, PisteSegment, Piste
from core.models import UserProfile
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, LineString
from django.db.models import F, Count
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Exists, OuterRef, Subquery
from django.core.cache import cache
from django.db import transaction
import numpy as np
from .utils import get_turning_points, completeness
from .badges import assign_badges
from cost.prices import get_daypass_price
from cost.seasonpass import has_seasonpass



from .strava_interface import load_activities, load_activity, load_activity_streams, load_activity_laps, update_activity_description, StravaWritePermissionError

# Get an instance of a logger
logger = logging.getLogger('core')


@dataclass
class ActivityParserConfig:
    """Configuration settings for the activity parser."""
    DEFAULT_MAX_DISTANCE: int = 250
    DEFAULT_BUFFER_METERS: int = 200
    CACHE_TIMEOUT_SECONDS: int = None # no expiration
    MAX_SPATIAL_INDEX_ENTRIES: int = 300
    MIN_LAPS_FOR_SPLIT: int = 30
    OLD_ACTIVITY_CUTOFF_YEAR: int = 2019
    GRAPH_MAX_AREA: int = 20_000
    GRAPH_MAX_DISTANCE: int = 500
    GRAPH_MAX_WALKING_CONNECTIONS: int = 10
    CACHE_RADIUS_METERS: int = 5000
    TURNING_POINT_PROMINENCE: int = 100
    LAP_POSITION_OFFSET: int = 5
    DEGREE_TO_METERS_APPROX: float = 111320.0
    MIN_LIFT_DISTANCE_METERS: int = 200
    NOTIFY_ADMIN: bool = True
    ADMIN_EMAIL: str = os.environ.get('ADMIN_EMAIL')
    FROM_EMAIL: str = os.environ.get('DEFAULT_FROM_EMAIL')

class ProfileManager:
    """Manages timing and profiling information for activity parsing operations."""

    def __init__(self, parser: "ActivityParser"):
        self.timings: Dict[str, List[float]] = defaultdict(list)
        self.call_counts: Dict[str, int] = defaultdict(int)
        self.current_operations: Dict[str, float] = {}
        self.parser = parser

    def start_operation(self, operation_name: str) -> None:
        """Start timing an operation."""
        self.current_operations[operation_name] = time.time()
        self.call_counts[operation_name] += 1
        logger.debug(f"Started operation '{operation_name}'")

    def end_operation(self, operation_name: str) -> float:
        """End timing an operation and return the duration."""
        if operation_name not in self.current_operations:
            logger.warning(f"Attempted to end operation '{operation_name}' that was never started")
            return 0.0

        start_time = self.current_operations.pop(operation_name)
        duration = time.time() - start_time
        self.timings[operation_name].append(duration)
        logger.debug(f"Ended operation '{operation_name}', duration: {duration:.4f}s")
        return duration

    def get_stats(self, operation_name: str) -> Dict[str, Any]:
        """Get statistics for a specific operation."""
        if operation_name not in self.timings or not self.timings[operation_name]:
            return {
                'total_time': 0,
                'avg_time': 0,
                'min_time': 0,
                'max_time': 0,
                'call_count': self.call_counts.get(operation_name, 0)
            }

        times = self.timings[operation_name]
        return {
            'total_time': sum(times),
            'avg_time': sum(times) / len(times),
            'min_time': min(times),
            'max_time': max(times),
            'call_count': self.call_counts[operation_name]
        }

    def get_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get summary statistics for all operations."""
        return {op: self.get_stats(op) for op in self.timings.keys()}

    def log_summary(self) -> None:
        """Log a summary of all profiling data."""
        summary = self.get_summary()
        logger.info("Activity Parser Performance Summary:")
        for operation, stats in summary.items():
            logger.info(f"  {operation}: {stats['call_count']} calls, "
                       f"total: {stats['total_time']:.4f}s, avg: {stats['avg_time']:.4f}s")
            
    def notify_admin(self) -> None:
        """Notify admin with profiling summary via email."""
        try:
            from django.core.mail import send_mail
            activity = self.parser.activity
            summary = self.get_summary()
            message_lines = [f"Activity Parser Performance Summary for activity {activity.id} v{activity.version} from user {activity.user.id}:"]
            for operation, stats in summary.items():
                message_lines.append(
                    f"{operation}: {stats['call_count']} calls, "
                    f"total: {stats['total_time']:.4f}s, avg: {stats['avg_time']:.4f}s"
                )
            message_lines.append(f"Total processing time: {activity.processing_time.total_seconds() if activity.processing_time else 'N/A'} seconds")
            message = "\n".join(message_lines)
            send_mail(
                subject="Activity Parser Performance Summary",
                message=message,
                from_email=ActivityParserConfig.FROM_EMAIL,
                recipient_list=[ActivityParserConfig.ADMIN_EMAIL],
            )
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}", exc_info=True, stack_info=True)

    def persist_stats(self) -> None:
        """Persist profiling stats to the database."""
        try:
            from activities.models import ActivityParserProfile
            activity = self.parser.activity
            summary = self.get_summary()
            for operation, stats in summary.items():
                ActivityParserProfile.objects.update_or_create(
                    activity_id=activity.id,
                    version=activity.version,
                    operation=operation,
                    defaults={
                        'call_count': stats['call_count'],
                        'total_time': stats['total_time'],
                        'avg_time': stats['avg_time'],
                        'min_time': stats['min_time'],
                        'max_time': stats['max_time'],
                    }
                )
        except Exception as e:
            logger.error(f"Failed to persist profiling stats: {e}", exc_info=True, stack_info=True)


class ActivityParser:
    """Main class for parsing Strava activities with profiling and caching capabilities."""

    def __init__(self, config: Optional[ActivityParserConfig] = None):
        
        self.activity = None
        self.timezone = None
        self.config = config or ActivityParserConfig()
        self.profiler = ProfileManager(self)
        self._cached_ski_areas: Dict[str, SkiArea] = {}
        self._cached_station_ids: Dict[str, List[int]] = {}
        self._cached_graphs: Dict[str, Dict] = {}

    def _make_timezone_aware(self, dt: datetime, tz_string: Optional[str]) -> datetime:
        """Convert naive datetime to timezone-aware using Strava timezone string."""
        logger.debug(f"_make_timezone_aware called with dt={dt}, tz_string={tz_string}")
        logger.debug(f"Input datetime is_aware: {timezone.is_aware(dt)}, tzinfo: {dt.tzinfo}")

        if not tz_string:
            logger.warning(f"No timezone string provided, using UTC for datetime {dt}")
            self.timezone = pytz.UTC
            result = pytz.UTC.localize(dt)
            logger.debug(f"Result after UTC localize: {result}, is_aware: {timezone.is_aware(result)}")
            return result

        # Extract timezone name from Strava format like "(GMT+01:00) Europe/Zurich"
        # Look for the part after ") " which should be the timezone name
        match = re.search(r'\)\s+(.+)$', tz_string)
        if match:
            tz_name = match.group(1)
            logger.debug(f"Extracted timezone name from regex: '{tz_name}'")
        else:
            # Fallback: use the original string
            tz_name = tz_string
            logger.debug(f"Using original string as timezone name: '{tz_name}'")

        try:
            tz = pytz.timezone(tz_name)
            self.timezone = tz
            result = tz.localize(dt)
            logger.debug(f"Successfully localized to {tz_name}: {result}, tzinfo: {result.tzinfo}")
            return result
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone '{tz_name}' from Strava timezone '{tz_string}', using UTC")
            self.timezone = pytz.UTC
            result = pytz.UTC.localize(dt)
            logger.debug(f"Fallback to UTC: {result}")
            return result

    def apply_exceptions(self, aerialway: Aerialway) -> Aerialway:

        # replace Parsennhüttenbahn with Totalp - next to each other
        if aerialway.way.osm_id == 29258980:
            return Aerialway.objects.get(way__osm_id = 20011874)

        return aerialway


    def get_osm_url(self, point: Point) -> str:
        """Generate OSM URL for a given point."""
        return f"https://www.openstreetmap.org/?mlat={point.y}&mlon={point.x}#map=17/{point.y}/{point.x}"


    def create_point(self, lat_field: str, lon_field: str, data: Dict[str, Any]) -> Optional[Point]:
        """Create a Point from latitude and longitude fields in data."""
        self.profiler.start_operation('create_point')
        if lat_field in data and lon_field in data:
            lon = data[lon_field] / 11930465
            lat = data[lat_field] / 11930465
            point = Point(lon, lat)
            duration = self.profiler.end_operation('create_point')
            logger.debug(f"Created point: {point} (took {duration:.4f} seconds)")
            return point
        self.profiler.end_operation('create_point')
        return None


    def add_lift_ride(self, aerialway: Aerialway, lift_ride: LiftRide,
                     before: Optional[bool] = None, after: Optional[bool] = None) -> None:
        """
        Adds a lift ride to a lap.
        If before is True, the lift ride is added before the lift ride.
        If after is True, the lift ride is added after the lift ride.
        """
        if before:
            timestamp = lift_ride.timestamp - timedelta(seconds=1)
        elif after:
            timestamp = lift_ride.timestamp + timedelta(seconds=1)
        else:
            raise ValueError("Either before or after must be True")

        new_lift_ride = LiftRide.create(
            lap=lift_ride.lap,
            aerialway=aerialway,
            timestamp=timestamp,
            uphill=False,
        )
        new_lift_ride.save()

    def get_ski_area_boundary(self, point: Point, buffer: int = 0) -> Optional[SkiAreaBoundary]:
        """
        Finds the ski area boundary containing the given point.
        If buffer > 0, it expands the search to ski areas within the buffered distance.

        :param point: A GeoDjango Point object (longitude, latitude)
        :param buffer: Optional buffer distance in meters
        :return: SkiAreaBoundary object or None if no match found
        """
        self.profiler.start_operation('get_ski_area_boundary')

        if buffer > 0:
            # Find ski areas where the point is within a buffered geometry
            ski_area_boundary = SkiAreaBoundary.objects.filter(
                geom__dwithin=(point, buffer)
            ).annotate(
                distance=Distance("geom", point)
            ).order_by("distance").first()
        else:
            # Find the ski area that directly contains the point
            ski_area_boundary = SkiAreaBoundary.objects.filter(geom__contains=point).first()

        self.profiler.end_operation('get_ski_area_boundary')
        return ski_area_boundary


    def get_ski_area(self, point: Point, buffer: int = 0) -> Optional[SkiArea]:
        """
        Finds the ski area containing the given point.
        If buffer > 0, it expands the search to ski areas within the buffered distance.

        :param point: A GeoDjango Point object (longitude, latitude)
        :param buffer: Optional buffer distance in meters
        :return: SkiArea object or None if no match found
        """
        self.profiler.start_operation('get_ski_area')

        # Check cache first
        cache_key = f"{point.x:.6f}_{point.y:.6f}_{buffer}"
        if cache_key in self._cached_ski_areas:
            self.profiler.end_operation('get_ski_area')
            return self._cached_ski_areas[cache_key]

        ski_areas = SkiArea.objects.filter(geom__isnull=False)

        if buffer > 0:
            # Find ski areas where the point is within a buffered geometry
            ski_area = ski_areas.filter(geom__dwithin=(point, buffer)).annotate(
                distance=Distance("geom", point)
            ).order_by("distance").first()
        else:
            # Find the ski area that directly contains the point
            ski_area = ski_areas.filter(geom__contains=point).first()

        # Cache the result
        self._cached_ski_areas[cache_key] = ski_area

        self.profiler.end_operation('get_ski_area')
        return ski_area



    def get_closest_aerialways(self, point: Point, in_ski_area: bool = False,
                              max_distance: int = 250, bottom_only: bool = False,
                              top_only: bool = False, use_nodes: bool = False) -> List[Aerialway]:
        """Find the closest aerialways to a given point."""

        logger.debug(f"Finding closest aerialways to {point} (in_ski_area={in_ski_area}, "
                    f"max_distance={max_distance}, bottom_only={bottom_only}, "
                    f"top_only={top_only}, use_nodes={use_nodes})")
        logger.debug(f"OSM URL: {self.get_osm_url(point)}")

        self.profiler.start_operation('get_closest_aerialways')
        point.srid = 4326
    
        aerialways = Aerialway.objects.all()
        
        if in_ski_area:
            aerialways = aerialways.filter(way__ski_areas__isnull=False)

        if bottom_only and top_only:
            raise ValueError("Cannot filter for bottom and top stations at the same time")
        
        if use_nodes:
            
            logger.debug("Using all nodes to find closest aerialways")
            
            nearest_node_distance = (
                Node.objects.filter(waynode__way__aerialway=OuterRef("pk"))  # Get nodes related to aerialway
                .annotate(distance=Distance("geom", point))  # Calculate distance to point
                .order_by("distance")  # Order by closest
                .values("distance")[:1]  # Take the closest node's distance
            )

            aerialways = Aerialway.objects.annotate(
                distance=Subquery(nearest_node_distance)
            )

            aerialways.order_by("distance")

            logger.debug(aerialways.query)
            logger.debug(aerialways[:100])

        else:
            aerialways = aerialways.annotate(distance=Distance("station_nodes__node__geom", point))
        
            closest_aerialways = (
                aerialways.filter(distance__lte=max_distance)
                .order_by("distance")
            )

            duration = self.profiler.end_operation('get_closest_aerialways')
            if closest_aerialways:
                logger.debug(f"Found closest aerialways: {closest_aerialways} (took {duration:.4f} seconds)")
            else:
                logger.debug(f"No closest aerialway found (took {duration:.4f} seconds)")

            return closest_aerialways


    def get_closest_stations(self, point: Point, max_distance: int = 250,
                           bottom_only: bool = False, top_only: bool = False) -> List[Station]:
        """Find the closest stations to a given point."""

        self.profiler.start_operation('get_closest_stations')
        point.srid = 4326

        # Check cache first
        cache_key = f"stations_{point.x:.6f}_{point.y:.6f}_{max_distance}_{bottom_only}_{top_only}"
        if cache_key in self._cached_station_ids:
            # Cache hit: retrieve stations by IDs to maintain order
            station_ids = self._cached_station_ids[cache_key]
            if station_ids:
                # Preserve order from cache using id__in and a custom ordering
                id_order = {id_: index for index, id_ in enumerate(station_ids)}
                cached_stations = Station.objects.filter(id__in=station_ids)
                result_list = sorted(cached_stations, key=lambda s: id_order[s.id])
            else:
                result_list = []

            self.profiler.end_operation('get_closest_stations')
            return result_list

        stations = Station.objects.all()

        if bottom_only and top_only:
            raise ValueError("Cannot filter for bottom and top stations at the same time")

        if bottom_only:
            stations = stations.filter(station = "bottom")

        if top_only:
            stations = stations.filter(station = "top")

        stations = stations.annotate(distance=Distance("node__geom", point))

        closest_stations = (
            stations.filter(distance__lte=max_distance)
            .order_by("distance")
        )

        duration = self.profiler.end_operation('get_closest_stations')

        # Cache only the IDs to save memory
        result_list = list(closest_stations)
        station_ids = [station.id for station in result_list]
        self._cached_station_ids[cache_key] = station_ids

        if result_list:
            logger.debug(f"Found closest stations: {result_list} (took {duration:.4f} seconds)")
        else:
            logger.debug(f"No closest stations found (took {duration:.4f} seconds)")

        return result_list


    def get_closest_aerialway(self, point: Point, in_ski_area: bool = False,
                             max_distance: int = 250, bottom_only: bool = False,
                             top_only: bool = False, use_nodes: bool = False) -> Optional[Aerialway]:
        """Get the closest single aerialway to a given point."""
        closest_aerialways = self.get_closest_aerialways(
            point, in_ski_area, max_distance, bottom_only, top_only, use_nodes
        )
        return closest_aerialways[0] if closest_aerialways else None


    def find_direct_lift(self, start: Point, end: Point) -> Tuple[Optional[Aerialway], bool]:
        """Finds a direct lift (Aerialway) connecting two points."""
        logger.debug(f"Finding direct lift between {start} and {end}")
        logger.debug(f"Start OSM URL Lift: {self.get_osm_url(start)}")
        logger.debug(f"End OSM URL Lift: {self.get_osm_url(end)}")

        self.profiler.start_operation('find_direct_lift')

        start_stations = self.get_closest_stations(start)
        end_stations = self.get_closest_stations(end)

        logger.debug(f"Lift Start stations: {start_stations}")
        logger.debug(f"Lift End stations: {end_stations}")

        # Get aerialways that have a start station
        aerialways_with_start = Aerialway.objects.filter(
            station_nodes__in=start_stations
        ).distinct()

        # Get aerialways that have an end station
        end_station_ids = [station.id for station in end_stations]
        direct_lift = aerialways_with_start.filter(
            Exists(
                Station.objects.filter(
                    aerialways=OuterRef("pk"),
                    id__in=end_station_ids  # Ensure correct filtering
                )
            )
        ).first()  # Fetch the first matching aerialway

        uphill = True
        if direct_lift:
            start_station = start_stations[0] if start_stations else None
            end_station = end_stations[0] if end_stations else None
            if start_station and end_station:
                uphill = not (start_station.station == "top" and end_station.station == "bottom")

        self.profiler.end_operation('find_direct_lift')
        logger.debug(f"Direct lift: {direct_lift}, uphill: {uphill}")
        return direct_lift, uphill


    def _find_nearby_cached_graph(self, start_point: Point, max_area: int,
                                 max_distance: int, max_walking_connections: int,
                                 cache_radius: int) -> Optional[Dict[str, Any]]:
        """Find cached graph for nearby points within cache_radius"""
        # Get spatial cache index
        spatial_index_key = f"spatial_cache_index_{max_area}_{max_distance}_{max_walking_connections}"
        spatial_index = cache.get(spatial_index_key, [])

        for entry in spatial_index:
            cached_point = Point(entry['x'], entry['y'])
            distance = start_point.distance(cached_point) * self.config.DEGREE_TO_METERS_APPROX

            if distance <= cache_radius:
                # Try to get the cached graph
                cached_data = cache.get(entry['cache_key'])
                if cached_data and isinstance(cached_data, dict) and 'graph' in cached_data:
                    return {
                        'graph': cached_data['graph'],
                        'cache_point': f"{entry['x']:.6f}, {entry['y']:.6f}",
                        'distance': distance
                    }

        return None


    def _store_spatial_cache_entry(self, point: Point, cache_key: str,
                                  max_area: int, max_distance: int,
                                  max_walking_connections: int) -> None:
        """Store cache entry in spatial index for nearby lookups"""
        spatial_index_key = f"spatial_cache_index_{max_area}_{max_distance}_{max_walking_connections}"
        spatial_index = cache.get(spatial_index_key, [])

        # Add new entry
        new_entry = {
            'x': point.x,
            'y': point.y,
            'cache_key': cache_key,
            'created_at': time.time()
        }

        # Remove old entries (keep only last entries to prevent memory bloat)
        # Only filter by time if CACHE_TIMEOUT_SECONDS is set
        if self.config.CACHE_TIMEOUT_SECONDS is not None:
            spatial_index = [entry for entry in spatial_index
                            if time.time() - entry.get('created_at', 0) < self.config.CACHE_TIMEOUT_SECONDS]
        spatial_index.append(new_entry)

        if len(spatial_index) > self.config.MAX_SPATIAL_INDEX_ENTRIES:
            # Keep only the most recent entries
            spatial_index = sorted(spatial_index, key=lambda x: x.get('created_at', 0))[
                            -self.config.MAX_SPATIAL_INDEX_ENTRIES:]

        # Store back in cache
        cache.set(spatial_index_key, spatial_index, self.config.CACHE_TIMEOUT_SECONDS)


    def build_lift_graph(self, start: Point, max_area: Optional[int] = None,
                        max_distance: Optional[int] = None,
                        max_walking_connections: Optional[int] = None) -> Dict[Station, List[Tuple[float, Station, Optional[Aerialway]]]]:
        """Builds a graph of aerialways and walking connections within the specified area of the start position."""

        # Use config defaults if not specified
        max_area = max_area or self.config.GRAPH_MAX_AREA
        max_distance = max_distance or self.config.GRAPH_MAX_DISTANCE
        max_walking_connections = max_walking_connections or self.config.GRAPH_MAX_WALKING_CONNECTIONS

        self.profiler.start_operation('build_lift_graph')

        # Try to find cached graph for nearby points
        cached_result = self._find_nearby_cached_graph(
            start, max_area, max_distance, max_walking_connections, self.config.CACHE_RADIUS_METERS
        )
        if cached_result:
            logger.info(f"Retrieved nearby cached lift graph for {start} (cache point: {cached_result['cache_point']})")
            self.profiler.end_operation('build_lift_graph')
            return cached_result['graph']

        # Create cache key for this exact location
        cache_data = f"{start.x:.6f}_{start.y:.6f}_{max_area}_{max_distance}_{max_walking_connections}"
        cache_key = f"lift_graph_{hashlib.md5(cache_data.encode()).hexdigest()}"

        logger.info("Building lift graph")

        graph = {}

        # **Filter stations within specified area of start**
        logger.info(f"Filtering stations within {max_area}m of start position")
        nearby_stations = Station.objects.select_related('node').annotate(
            distance=Distance("node__geom", start)
        ).filter(distance__lte=max_area)

        # **Filter aerialways whose stations are within the area**
        logger.info(f"Filtering aerialways with stations within {max_area}m of start position")
        nearby_aerialways = Aerialway.objects.filter(
            station_nodes__in=nearby_stations
        ).distinct().prefetch_related("station_nodes")

        # **Add direct lift connections**
        logger.info("Number of nearby aerialways: %s", nearby_aerialways.count())
        logger.info("Number of nearby stations: %s", nearby_stations.count())
        logger.info("Adding direct lift connections")
        for aerialway in nearby_aerialways:
            stations = list(aerialway.station_nodes.all())
            for i in range(len(stations) - 1):
                station_a, station_b = stations[i], stations[i + 1]
                distance = station_a.node.geom.distance(station_b.node.geom)
                graph.setdefault(station_a, []).append((distance, station_b, aerialway))
                graph.setdefault(station_b, []).append((distance, station_a, aerialway))

        # **Add walking connections within max_distance (limited to prevent O(n²) scaling)**
        logger.info("Adding walking connections")
        for station in nearby_stations:
            # Skip stations that already have many lift connections
            existing_connections = len(graph.get(station, []))
            if existing_connections >= 3:  # Already well-connected via lifts
                continue

            # Get only the closest walking connections to prevent O(n²) scaling
            nearby_walkable_stations = (
                nearby_stations.annotate(distance=Distance(F("node__geom"), station.node.geom))
                .filter(distance__lte=max_distance)
                .exclude(id=station.id)  # Exclude itself
                .order_by('distance')[:max_walking_connections]  # Limit to closest N connections
            )

            for nearby_station in nearby_walkable_stations:
                distance = station.node.geom.distance(nearby_station.node.geom)
                graph.setdefault(station, []).append((distance, nearby_station, None))
                graph.setdefault(nearby_station, []).append((distance, station, None))  # Add both directions

        duration = self.profiler.end_operation('build_lift_graph')
        logger.info(f"Built lift graph in {duration:.4f} seconds")

        # Cache the graph with metadata
        cache_data = {
            'graph': graph,
            'center_point': {'x': start.x, 'y': start.y},
            'max_area': max_area,
            'max_distance': max_distance,
            'max_walking_connections': max_walking_connections,
            'created_at': time.time()
        }
        cache.set(cache_key, cache_data, self.config.CACHE_TIMEOUT_SECONDS)

        # Also store in a spatial index for nearby lookups
        self._store_spatial_cache_entry(start, cache_key, max_area, max_distance, max_walking_connections)

        logger.info(f"Cached lift graph for {start}")

        return graph

    def dijkstra(self, start_nodes: List[Station], end_nodes: List[Station],
                graph: Dict[Station, List[Tuple[float, Station, Optional[Aerialway]]]]) -> List[Station]:
        """Finds the shortest path between any start node and any end node."""
        logger.info("Running Dijkstra's algorithm")
        self.profiler.start_operation('dijkstra')

        queue = [(0, id(start_node), start_node, []) for start_node in start_nodes]
        visited = set()
        path = None

        while queue:
            dist, _, current, path = heapq.heappop(queue)  # Pop the node with the smallest distance, then tie break by id
            if current in visited:
                continue
            visited.add(current)
            path = path + [current]

            if current in end_nodes:
                duration = self.profiler.end_operation('dijkstra')
                logger.info(f"Found path in {duration:.4f} seconds")
                return path  # Return path if any destination is reached

            for weight, neighbor, aerialway in graph.get(current, []):
                if neighbor not in visited:
                    heapq.heappush(queue, (dist + weight, id(neighbor), neighbor, path))

        duration = self.profiler.end_operation('dijkstra')
        logger.warning("No path found in %s seconds", duration)
        return []  # No path found

    def get_aerialways(self, start: Optional[Point] = None, end: Optional[Point] = None,
                      start_activity: Optional[Point] = None) -> List[Tuple[Aerialway, bool]]:
        """Find aerialways connecting two points or the closest aerialway to a single point."""

        self.profiler.start_operation('get_aerialways')

        uphill = True
        if start is None or end is None:
            if start is None and end is not None:
                aerialway = self.get_closest_aerialway(end)
            elif end is None and start is not None:
                aerialway = self.get_closest_aerialway(start)
            else:
                aerialway = None

            self.profiler.end_operation('get_aerialways')
            if aerialway:
                return [(aerialway, uphill)]
            else:
                return []

        direct_lift, uphill = self.find_direct_lift(start, end)
        if direct_lift:
            self.profiler.end_operation('get_aerialways')
            return [(direct_lift, uphill)]

        # Find all nearby stations for start and end
        max_distance = self.config.DEFAULT_MAX_DISTANCE
        start_stations = self.get_closest_stations(start, max_distance=max_distance)
        end_stations = self.get_closest_stations(end, max_distance=max_distance)

        if not start_stations or not end_stations:
            logger.debug("No valid stations found, trying to find aerialway without stations")

            lift = self._find_aerialway_fallback(start, end, start_stations, end_stations)

            self.profiler.end_operation('get_aerialways')
            if lift:
                return [(lift, uphill)]
            else:
                return []  # No valid stations found

        if start_activity:
            graph = self.build_lift_graph(start_activity)
            logger.debug("graph built from activity start point")
        else:
            graph = self.build_lift_graph(start)
            logger.debug("graph built from start point")

        # Get the shortest station path from multiple start and end stations
        station_path = self.dijkstra(start_stations, end_stations, graph)
        if not station_path and start_activity:
            # try again with start point if path not found on graph centered on activity start
            logger.debug("No path found, trying again with graph centered on start point")
            graph = self.build_lift_graph(start)
            station_path = self.dijkstra(start_stations, end_stations, graph)

        logger.debug(f"Station path: {station_path}")

        for station in station_path:
            try:
                logger.debug(station.get_osm_url())
            except Exception as e:
                logger.debug(f"Could not get OSM URL for station {station}: {e}")

        # Extract aerialways from station path
        aerialway_path = []

        for i in range(len(station_path) - 1):
            station_a, station_b = station_path[i], station_path[i + 1]

            logger.debug(f"Connection: {station_a} -> {station_b}")
            logger.debug(graph[station_a])

            connection = next(
                (aerialway for _, neighbor, aerialway in graph[station_a] if neighbor == station_b and aerialway),
                None
            )

            logger.debug(connection if connection else "No connection found")

            uphill = True
            if connection:
                if station_a.station == "top" or station_b.station == "bottom":
                    uphill = False
                aerialway_path.append((connection, uphill))

        logger.debug(f"Aerialway path: {aerialway_path}")
        self.profiler.end_operation('get_aerialways')
        return aerialway_path

    def _find_aerialway_fallback(self, start: Point, end: Point,
                                start_stations: List[Station],
                                end_stations: List[Station]) -> Optional[Aerialway]:
        """Fallback method to find aerialways when no direct stations are found."""
        lift = None

        if start_stations:
            # Find aerialways that have at least one of the start stations
            aerialways = Aerialway.objects.filter(station_nodes__in=start_stations)

            # Subquery to find the closest node from the aerialway's way to `end`
            nearest_node_distance = (
                Node.objects.filter(waynode__way__aerialway=OuterRef("pk"))  # Get all nodes for each aerialway
                .annotate(distance=Distance("geom", end))  # Compute distance from node to `end`
                .order_by("distance")  # Sort by closest node
                .values("distance")[:1]  # Select the closest node distance
            )

            # Annotate aerialways with the closest node distance
            aerialways = aerialways.annotate(distance=Subquery(nearest_node_distance))

            # Get the closest aerialway
            lift = aerialways.order_by("distance").first()

        if not lift and end_stations:  # Only check end stations if no lift was found
            aerialways = Aerialway.objects.filter(station_nodes__in=end_stations)

            # Subquery to find the closest node from the aerialway's way to `start`
            nearest_node_distance = (
                Node.objects.filter(waynode__way__aerialway=OuterRef("pk"))
                .annotate(distance=Distance("geom", start))
                .order_by("distance")
                .values("distance")[:1]
            )

            aerialways = aerialways.annotate(distance=Subquery(nearest_node_distance))
            lift = aerialways.order_by("distance").first()

        # use closer distance as we are using all nodes including waypoints
        if not lift:
            logger.debug("No valid stations found, trying to find aerialway with all nodes")
            lift = self.get_closest_aerialway(start, max_distance=100, use_nodes=True)

        if not lift:
            logger.debug("No valid stations found, trying to find aerialway with all nodes")
            lift = self.get_closest_aerialway(end, max_distance=100, use_nodes=True)

        logger.debug(lift)
        return lift

    def split_activity(self, activity: Activity, activity_streams: Dict[str, Any]) -> None:
        """
        Splits a single activity into multiple laps based on the activity streams.
        """
        self.profiler.start_operation('split_activity')

        lap_data = []

        turning_points = get_turning_points(activity_streams["altitude"].data,
                                          prominence=self.config.TURNING_POINT_PROMINENCE)

        diff = np.diff(activity_streams["altitude"].data)
        logger.debug(f"Number of turning points: {len(turning_points)}")
        for i, (index, direction) in enumerate(turning_points):
            logger.debug(f"Turning point {i+1}: {index}, {direction}")
            logger.debug(f"OSM URL: {self.get_osm_url(Point(activity_streams['latlng'].data[index][1], activity_streams['latlng'].data[index][0]))}")
            if direction == "peak":
                next = turning_points[i+1][0] if i+1 < len(turning_points)-1 else len(activity_streams["altitude"].data)-1
                lap_diff = diff[index:next]
                lap_data.append({
                    "timestamp": activity.start_time + timedelta(seconds=activity_streams["time"].data[index]),
                    "start_time": activity.start_time + timedelta(seconds=activity_streams["time"].data[index]),
                    "end_time": activity.start_time + timedelta(seconds=activity_streams["time"].data[next]),
                    "start_position": Point(activity_streams["latlng"].data[index][1], activity_streams["latlng"].data[index][0]),
                    "end_position": Point(activity_streams["latlng"].data[next][1], activity_streams["latlng"].data[next][0]),
                    "total_elapsed_time": timedelta(seconds=activity_streams["time"].data[next] - activity_streams["time"].data[index]),
                    "total_timer_time": timedelta(seconds=activity_streams["time"].data[next] - activity_streams["time"].data[index]),
                    "total_distance": activity_streams["distance"].data[next] - activity_streams["distance"].data[index],
                    "total_ascent": np.sum(lap_diff[lap_diff > 0]),
                    "total_descent": np.sum(np.abs(lap_diff[lap_diff < 0])),
                    "start_index_stream": index,
                    "end_index_stream": next,
                })

        total_distance = sum(lap['total_distance'] for lap in lap_data)
        total_descent = sum(lap['total_descent'] for lap in lap_data)
        total_ascent = sum(lap['total_ascent'] for lap in lap_data)
        activity.total_distance = total_distance
        activity.total_descent = total_descent
        activity.total_ascent = total_ascent
        activity.save()

        for i, lap_data_item in enumerate(lap_data):
            lap_instance, created = Lap.objects.update_or_create(lap_index=i+1, activity=activity, defaults=lap_data_item)
            try:
                lap_instance.geom = LineString([
                    (
                        activity_streams["latlng"].data[i][1],
                        activity_streams["latlng"].data[i][0]
                    )
                    for i in range(lap_instance.start_index_stream, lap_instance.end_index_stream - 5)
                ], srid=4326)
                lap_instance.save()
            except Exception as e:
                logger.error(f"Error setting geometry for lap {lap_instance.lap_index} of activity {activity.id}: {e}")

        self.profiler.end_operation('split_activity')


    def assign_cost(self, activity: Activity) -> None:
        """Assign cost to an activity based on ski area pricing."""
        self.profiler.start_operation('assign_cost')

        skiarea = activity.ski_area
        if not skiarea:
            logger.warning(f"No ski area found for activity, no cost assigned: {activity.id}")
            self.profiler.end_operation('assign_cost')
            return

        user = activity.user
        date = activity.start_time.date()
        cost = get_daypass_price(skiarea, date, user)

        seasonpass = has_seasonpass(user, skiarea, date)
        if seasonpass:
            logger.debug(f"User {user.username} has a season pass for ski area {skiarea.name}")
            activity.cost = 0
            activity.value = cost
        else:
            activity.cost = cost
            activity.value = cost
        activity.save()
        logger.info(f"Assigned cost {activity.cost} to activity {activity.id}")
        self.profiler.end_operation('assign_cost')


    def calc_vertical_lap(self, lap: Lap, altitude_stream: List[float], update: bool = True) -> None:
        """
        Calculate the total ascent and descent for a lap.
        """
        self.profiler.start_operation('calc_vertical_lap')
        diffs = np.diff(altitude_stream[lap.start_index_stream:lap.end_index_stream])
        lap.total_ascent = np.sum(diffs[diffs > 0])
        lap.total_descent = np.sum(np.abs(diffs[diffs < 0]))
        if update:
            lap.save()
        self.profiler.end_operation('calc_vertical_lap')


    def calc_vertical_activity(self, activity: Activity, altitude_stream: List[float], update: bool = True) -> None:
        """
        Calculate the total ascent and descent for an activity.
        """
        self.profiler.start_operation('calc_vertical_activity')
        total_ascent = 0
        total_descent = 0
        for lap in activity.laps.all():
            if update:
                self.calc_vertical_lap(lap, altitude_stream, update=True)
            total_ascent += lap.total_ascent
            total_descent += lap.total_descent
        activity.total_ascent = total_ascent
        activity.total_descent = total_descent
        if update:
            activity.save()
        self.profiler.end_operation('calc_vertical_activity')


    def calc_line_geom(self, activity: Activity, latlng_stream: Optional[List[List[float]]] = None) -> None:
        """Calculate and save the geometry for an activity."""
        self.profiler.start_operation('calc_line_geom')

        if latlng_stream:
            logger.debug(f"latlng stream: {latlng_stream[0:50]}")
            swapped_coords = [(lon, lat) for lat, lon in latlng_stream]
            activity.geom = LineString(swapped_coords)
            activity.save()
            self.profiler.end_operation('calc_line_geom')
            return

        if activity.polyline:
            coords = polyline.decode(activity.polyline)
        elif activity.summary_polyline:
            coords = polyline.decode(activity.summary_polyline)
        else:
            logger.error(f"No polyline found for activity: {activity.id}", exc_info=True, stack_info=True)
            self.profiler.end_operation('calc_line_geom')
            return

        # Swap lat/lon to lon/lat
        swapped_coords = [(lon, lat) for lat, lon in coords]

        # Save as LineString with correct coordinate order
        activity.geom = LineString(swapped_coords, srid=4326)
        activity.save()

        logger.info(f"Saved geometry for activity {activity.id} with {len(swapped_coords)} points")
        self.profiler.end_operation('calc_line_geom')


    def calc_ridden_segments(self, activity: Activity) -> None:
        """Calculate piste segments ridden during an activity."""
        self.profiler.start_operation('calc_ridden_segments')
        logger.info(f"Calculating segments for activity: {activity.strava_id}")

        if not activity.geom:
            self.calc_line_geom(activity)

        buffer_width = self.config.DEFAULT_BUFFER_METERS / 40000000 * 360  # roughly 100 meters
        buffered_geom = activity.geom.buffer(buffer_width)
        segments = PisteSegment.objects.filter(geom__coveredby=buffered_geom)

        for segment in segments:
            logger.debug(f"Found segment: {segment}")

        logger.info(f"Found {segments.count()} segments for activity: {activity.strava_id}")

        # Delete old segment assignments to avoid duplicates
        ActivityPisteSegment.objects.filter(activity=activity).delete()

        # Create new ActivityPisteSegment relationships
        activity_piste_segments = [
            ActivityPisteSegment(activity=activity, piste_segment=segment) for segment in segments
        ]
        ActivityPisteSegment.objects.bulk_create(activity_piste_segments)

        # TODO: create warning if created segments are significantly shorter or longer than activity distance

        duration = self.profiler.end_operation('calc_ridden_segments')
        logger.info(f"Found {segments.count()} segments for activity: {activity.strava_id}")
        logger.info(f"Calculated segments for activity: {activity.strava_id} in {duration:.4f} seconds")
    

    @transaction.atomic
    def sync_strava_activity(self, user: User, activity_id: str, update: bool = False) -> Optional[Activity]:
        start_time = time.time()
        logger.info(f"Starting to parse Strava activity: {activity_id} for user: {user.username}, update: {update}")

        try:
            exists = Activity.objects.filter(strava_id=activity_id).exists()
            logger.debug(f"Activity {activity_id} exists: {exists}")

            if not update and exists:
                logger.info(f"Strava activity {activity_id} already exists in the database.")
                return Activity.objects.get(strava_id=activity_id)

            # Load Strava data
            activity = load_activity(user, activity_id)
            if not activity:
                logger.error(f"Strava activity {activity_id} not found", exc_info=True, stack_info=True)
                raise ValueError(f"Strava activity {activity_id} not found")

            if not activity.type == 'AlpineSki':
                logger.warning(f"Strava activity {activity_id} is not an AlpineSki activity.")
                return None

            activity_streams = load_activity_streams(user, activity_id)
            activity_laps = load_activity_laps(user, activity_id)

            # Process the activity using the new structured approach
            activity_instance, was_created = self._process_strava_activity(
                activity, activity_streams, activity_laps, user, activity_id, update
            )

            # Finalize processing
            self._finalize_activity_processing(activity_instance, activity_streams, was_created)

            # Update processing metadata
            activity_instance.processing_time = timedelta(seconds=time.time() - start_time)
            activity_instance.processed_on = timezone.now()
            activity_instance.save()

            logger.info(f"Finished parsing Strava activity: {activity_id} in {time.time() - start_time:.4f} seconds")
            return activity_instance

        except Exception as e:
            logger.error(f"Error parsing Strava activity {activity_id}: {str(e)}", exc_info=True, stack_info=True)
            raise

    def _process_strava_activity(self, activity, activity_streams, activity_laps, user: User, activity_id: str, update: bool) -> Tuple[Activity, bool]:
        """Process the core Strava activity data and create/update the Activity instance.

        Returns:
            Tuple[Activity, bool]: (activity_instance, was_created)
        """
        self.profiler.start_operation('process_strava_activity')

        # Extract start point and find ski area
        lat, lon = activity_streams["latlng"].data[0]
        start_point = Point(lon, lat)

        start_lift = self.get_closest_aerialway(start_point, in_ski_area=True, max_distance=2000)
        ski_area = self.get_ski_area(start_point)

        if not ski_area and start_lift:
            logger.warning(f"No ski area found for activity: {activity_id}, searching relations")
            ski_area = SkiArea.objects.filter(ways=start_lift.way).first()
            logger.debug(f"Found ski area from relation: {ski_area}")

        # Create activity data structure
        logger.debug(f"Raw Strava activity data:")
        logger.debug(f"  activity.start_date_local: {activity.start_date_local}")
        logger.debug(f"  activity.start_date (UTC): {activity.start_date if hasattr(activity, 'start_date') else 'N/A'}")
        logger.debug(f"  activity.timezone: {activity.timezone}")

        activity_data = {
            "name": activity.name,
            "type": activity.type,
            "start_time": self._make_timezone_aware(activity.start_date_local, activity.timezone),
            "timestamp": self._make_timezone_aware(activity.start_date_local, activity.timezone),
            "timezone": str(self.timezone) if self.timezone else None,
            "summary_polyline": activity.map.summary_polyline,
            "polyline": None,
            "total_elapsed_time": timedelta(seconds=activity.elapsed_time),
            "total_timer_time": timedelta(seconds=activity.moving_time),
            "total_distance": activity.distance,
            "total_ascent": activity.total_elevation_gain,
            "avg_speed": activity.average_speed,
            "max_speed": activity.max_speed,
            "total_calories": activity.calories,
            "avg_heart_rate": activity.average_heartrate,
            "max_heart_rate": activity.max_heartrate,
            "user": user,
            "start_position": start_point,
            "ski_area": ski_area,
            "device_name": activity.device_name,
        }

        # Create or update activity
        activity_instance, created = Activity.objects.update_or_create(
            strava_id=activity_id, defaults=activity_data
        )
        self.activity = activity_instance
        logger.info(f'{"Created" if created else "Updated"} Activity: {activity_instance.id}')
        logger.debug(f"Saved activity times:")
        logger.debug(f"  start_time: {activity_instance.start_time}, tzinfo: {activity_instance.start_time.tzinfo}")
        logger.debug(f"  timestamp: {activity_instance.timestamp}, tzinfo: {activity_instance.timestamp.tzinfo}")

        # Handle updates
        if not created:
            activity_instance.version += 1
            activity_instance.laps.all().delete()
            logger.info(f"Deleted existing laps for Activity: {activity_instance.id}")

        # Process laps
        self._process_activity_laps(activity_instance, activity_laps, activity_streams)

        # Process lift rides
        self._process_lift_rides(activity_instance, activity_streams)

        self.profiler.end_operation('process_strava_activity')
        return activity_instance, created

    def _process_activity_laps(self, activity_instance: Activity, activity_laps, activity_streams) -> None:
        """Process and create lap instances from Strava lap data."""
        self.profiler.start_operation('process_activity_laps')

        activity_start_time = activity_instance.start_time

        # Convert to list to get length and ensure we can iterate multiple times
        activity_laps_list = list(activity_laps)
        logger.info(f"Processing {len(activity_laps_list)} laps for activity {activity_instance.id}")

        for lap in activity_laps_list:
            lap_data = {
                "start_time": activity_start_time + timedelta(seconds=activity_streams["time"].data[lap.start_index]),
                "timestamp": activity_start_time + timedelta(seconds=activity_streams["time"].data[lap.start_index]),
                "total_elapsed_time": timedelta(seconds=lap.elapsed_time),
                "total_timer_time": timedelta(seconds=lap.moving_time),
                "total_distance": lap.distance,
                "total_ascent": lap.total_elevation_gain,
                "start_index_stream": lap.start_index,
                "end_index_stream": lap.end_index,
                "avg_speed": lap.average_speed,
                "max_speed": lap.max_speed,
                "avg_heart_rate": lap.average_heartrate,
                "max_heart_rate": lap.max_heartrate,
                "start_position": Point(
                    activity_streams["latlng"].data[lap.start_index + self.config.LAP_POSITION_OFFSET][1],
                    activity_streams["latlng"].data[lap.start_index + self.config.LAP_POSITION_OFFSET][0]
                ),
                "end_position": Point(
                    activity_streams["latlng"].data[lap.end_index - self.config.LAP_POSITION_OFFSET][1],
                    activity_streams["latlng"].data[lap.end_index - self.config.LAP_POSITION_OFFSET][0]
                ),
                "end_time": activity_start_time + timedelta(seconds=activity_streams["time"].data[lap.end_index]),
            }
            lap_instance, created = Lap.objects.update_or_create(
                lap_index=lap.lap_index, activity=activity_instance, defaults=lap_data
            )
            try:
                lap_instance.geom = LineString([
                    (
                        activity_streams["latlng"].data[i][1],
                        activity_streams["latlng"].data[i][0]
                    )
                    for i in range(lap.start_index, lap.end_index - 5)
                ], srid=4326)
                lap_instance.save()
            except Exception as e:
                logger.error(f"Error setting geometry for lap {lap_instance.lap_index} of activity {activity_instance.id}: {e}")
            logger.info(f'{"Created" if created else "Updated"} Lap: {lap_instance.lap_index}')

        # Handle lap splitting for activities with insufficient auto-pause data
        if (activity_instance.laps.count() == 1 or
            (activity_instance.laps.count() > self.config.MIN_LAPS_FOR_SPLIT and
             activity_instance.timestamp.year < self.config.OLD_ACTIVITY_CUTOFF_YEAR)):
            logger.info("Splitting activity into custom laps based on elevation data")
            activity_instance.laps.all().delete()
            self.split_activity(activity_instance, activity_streams)

        self.profiler.end_operation('process_activity_laps')

    def _process_lift_rides(self, activity_instance: Activity, activity_streams) -> None:
        """Process and create lift ride instances for each lap."""
        self.profiler.start_operation('process_lift_rides')

        for lap in activity_instance.laps.all():
            logger.debug(f"Processing Lap: {lap.lap_index}")
            logger.debug(f"Start Position (Lap): {self.get_osm_url(lap.start_position)} at {lap.start_time}")
            logger.debug(f"End Position (Lap): {self.get_osm_url(lap.end_position)} at {lap.end_time}")

            # Determine lift start and end positions
            lift_end_pos = lap.start_position
            prev_lap = Lap.objects.filter(
                activity=activity_instance,
                lap_index=lap.lap_index - 1
            ).first()

            if prev_lap:
                lift_start_pos = prev_lap.end_position
                lift_start_time = prev_lap.end_time
                logger.debug(f"Distance to previous lap end: {lift_start_pos.distance(lap.start_position) * self.config.DEGREE_TO_METERS_APPROX:.2f} meters")
                if lift_start_pos.distance(lap.start_position) * self.config.DEGREE_TO_METERS_APPROX < self.config.MIN_LIFT_DISTANCE_METERS:
                    logger.debug("Lift start and end positions are too close, skipping lift ride detection for this lap")
                    continue
            else:
                lift_start_pos = None
                lift_start_time = lap.start_time

            # Find aerialways connecting the positions
            lift_rides = self.get_aerialways(
                lift_start_pos, lift_end_pos,
                start_activity=activity_instance.start_position
            )

            # Create lift ride instances
            for lift_ride, uphill in lift_rides:
                logger.debug(f"Found lift ride: {lift_ride.name if lift_ride else 'unnamed'}")
                logger.debug(f"Uphill: {uphill}")

                # Apply any lift exceptions/corrections
                lift_ride = self.apply_exceptions(lift_ride)

                # Create the lift ride
                lift, _ = LiftRide.objects.update_or_create(
                    lap=lap,
                    aerialway=lift_ride,
                    uphill=uphill,
                    timestamp=lift_start_time
                )

                # Advance timestamp for next potential lift ride
                duration_minutes = lift.aerialway.aerialway_duration if lift.aerialway.aerialway_duration else 1
                lift_start_time = lift_start_time + timedelta(minutes=duration_minutes)

                logger.info(f"Created LiftRide for Lap: {lap.lap_index} with lift {lift_ride.name if lift_ride else 'unnamed'}")

        self.profiler.end_operation('process_lift_rides')

    def _calculate_piste_coverage(self, piste: Piste, buffered_lap_geom) -> float:
        """
        Calculate what percentage of a piste is covered by the lap track.
        Handles both line-based and area-based pistes differently.

        Args:
            piste: The piste to check coverage for
            buffered_lap_geom: Lap geometry buffered by ~100m

        Returns:
            Coverage percentage (0-100)
        """
        if not piste.geom or piste.geom.empty:
            return 0.0

        try:
            # Get intersection of piste with buffered lap track
            intersection = piste.geom.intersection(buffered_lap_geom)

            if not intersection or intersection.empty:
                return 0.0

            # Determine if piste is area or line based on way nodes
            is_area = piste.is_area()

            if is_area:
                # For area pistes (closed ways), use area coverage
                # The buffered track intersection with the piste area
                covered_area = intersection.area if hasattr(intersection, 'area') else 0
                total_area = piste.geom.area

                if total_area <= 0:
                    return 0.0

                coverage_pct = (covered_area / total_area) * 100
                logger.debug(f"Piste {piste.id} is area-based (closed way): covered={covered_area:.6f}, total={total_area:.6f}")

            else:
                # For line pistes (open ways), use length coverage
                covered_length = intersection.length if hasattr(intersection, 'length') else 0
                total_length = piste.geom.length

                if total_length <= 0:
                    return 0.0

                coverage_pct = (covered_length / total_length) * 100
                logger.debug(f"Piste {piste.id} is line-based (open way): covered={covered_length:.6f}, total={total_length:.6f}")

            return min(coverage_pct, 100.0)  # Cap at 100%

        except Exception as e:
            logger.warning(f"Error calculating coverage for piste {piste.id}: {e}")
            return 0.0

    def _process_piste_rides(self, activity_instance: Activity, activity_streams=None) -> None:
        """
        Process and create piste ride instances based on 80% coverage threshold.

        A piste is considered "ridden" if 80% or more of its length intersects
        with a lap's GPS track (buffered by ~100m). Processing is done lap by lap
        to avoid counting pistes during lift rides (gaps between laps).

        Args:
            activity_instance: The activity to process
            activity_streams: Optional activity stream data (unused but kept for consistency)
        """
        self.profiler.start_operation('process_piste_rides')

        # Delete existing PisteRides for reprocessing
        lap_ids = activity_instance.laps.values_list('id', flat=True)
        PisteRide.objects.filter(lap_id__in=lap_ids).delete()

        # Track unique pistes by name across all laps to avoid duplicates
        # (some pistes are modeled as both line and area)
        seen_piste_names = {}  # name -> piste object (first occurrence)
        piste_rides_to_create = []

        # Buffer width for ~100 meters
        buffer_width = self.config.DEFAULT_BUFFER_METERS / 40000000 * 360

        # Process each lap separately
        laps = list(activity_instance.laps.all().order_by('lap_index'))
        logger.info(f"Processing {len(laps)} laps for activity {activity_instance.id}")

        for lap in laps:
            logger.debug(f"Processing lap {lap.lap_index} for activity {activity_instance.id}")

            lap_geom = lap.geom
            if not lap_geom:
                logger.warning(f"Lap {lap.lap_index} has no geometry, skipping piste ride processing")
                continue

            # Buffer the lap geometry
            buffered_lap_geom = lap_geom.buffer(buffer_width)

            # Find intersecting pistes for this lap
            intersecting_pistes = Piste.objects.filter(
                geom__intersects=buffered_lap_geom,
                geom__isnull=False,
            ).exclude(
                piste_difficulty='freeride'
            ).exclude(
                piste_grooming='backcountry'
            ).select_related('way')

            logger.debug(f"Lap {lap.lap_index}: Found {intersecting_pistes.count()} intersecting pistes")

            # Calculate coverage for each piste
            lap_ridden_pistes = []
            for piste in intersecting_pistes:
                coverage_pct = self._calculate_piste_coverage(piste, buffered_lap_geom)

                piste_name = piste.name or piste.ref or f"unnamed_{piste.id}"
                logger.debug(f"Lap {lap.lap_index} - Piste {piste.id} '{piste_name}': {coverage_pct:.1f}% coverage")

                if coverage_pct >= 80.0:
                    lap_ridden_pistes.append(piste)
                    logger.info(f"Lap {lap.lap_index} - Piste '{piste_name}' qualified with {coverage_pct:.1f}% coverage")

                    '''
                    # Check if we've already seen this piste name
                    if piste_name not in seen_piste_names:
                        seen_piste_names[piste_name] = piste
                        lap_ridden_pistes.append(piste)
                        logger.info(f"Lap {lap.lap_index} - Piste '{piste_name}' qualified with {coverage_pct:.1f}% coverage")
                    else:
                        # Skip duplicate (e.g., same piste as line and area)
                        logger.debug(f"Lap {lap.lap_index} - Skipping duplicate piste '{piste_name}' (already seen)")
                    '''
                    
            # Create PisteRides for this lap
            for piste_index, piste in enumerate(lap_ridden_pistes):
                # Calculate timestamp (sequential within lap)
                timestamp = lap.start_time + timedelta(seconds=piste_index)

                piste_rides_to_create.append(
                    PisteRide(
                        lap=lap,
                        piste=piste,
                        timestamp=timestamp
                    )
                )

            logger.debug(f"Lap {lap.lap_index}: {len(lap_ridden_pistes)} unique pistes qualified")

        # Bulk create all piste rides
        if piste_rides_to_create:
            PisteRide.objects.bulk_create(piste_rides_to_create)
            logger.info(f"Created {len(piste_rides_to_create)} PisteRides across {len(laps)} laps for activity {activity_instance.id}")
            logger.info(f"Unique pistes by name: {len(seen_piste_names)}")
        else:
            logger.info(f"No pistes met 80% threshold for activity {activity_instance.id}")

        self.profiler.end_operation('process_piste_rides')

    def _calculate_completeness(self, activity_instance: Activity) -> None:
        """Calculate and update completeness scores for activity, ski area, and pistes."""

        self.profiler.start_operation('calculate_completeness')

        self.profiler.start_operation('calculate_activity_completeness')
        completeness.calculate_activity_completeness(activity_instance)
        self.profiler.end_operation('calculate_activity_completeness')

        self.profiler.start_operation('calculate_activity_piste_completeness')
        completeness.calculate_activity_piste_completeness(activity_instance)
        self.profiler.end_operation('calculate_activity_piste_completeness')

        self.profiler.start_operation('calculate_ski_area_completeness')
        completeness.calculate_ski_area_completeness(user=activity_instance.user, ski_area=activity_instance.ski_area, force_calc=True)
        self.profiler.end_operation('calculate_ski_area_completeness')
        
        self.profiler.start_operation('calculate_ski_area_piste_completeness')
        completeness.calculate_ski_area_piste_completeness(user=activity_instance.user, ski_area=activity_instance.ski_area, force_calc=True)
        self.profiler.end_operation('calculate_ski_area_piste_completeness')

        from .utils.seasons import get_season_for_activity
        self.profiler.start_operation('calculate_ski_area_completeness')
        season_tuple = get_season_for_activity(activity_instance)
        season = f"{season_tuple[0]}-{season_tuple[1]}"
        completeness.calculate_ski_area_completeness(user=activity_instance.user, ski_area=activity_instance.ski_area, season=season, force_calc=True)
        self.profiler.end_operation('calculate_ski_area_completeness')

        self.profiler.end_operation('calculate_completeness')
    
    def generate_strava_description(self, activity_instance: Activity, existing_description: str = "") -> str:
        """
        Generate a description for the Strava activity with lift ride information.
        Uses a regex-matchable pattern to identify and replace our generated content while preserving user content.

        Pattern: 🎿 3x Tiefenbachbahn, 2x Schwarze Schneid, 1x Mutkogl - tracked by SlopeLog.com 🎿
        """
        self.profiler.start_operation('generate_strava_description')

        # Get all lift rides for this activity, grouped by aerialway
        lift_rides = LiftRide.objects.filter(
            lap__activity=activity_instance,
            uphill=True
        ).select_related('aerialway').order_by('timestamp')

        if not lift_rides.exists():
            self.profiler.end_operation('generate_strava_description')
            return existing_description

        # Count rides per lift
        from collections import Counter
        lift_counts = Counter()
        for ride in lift_rides:
            lift_counts[ride.aerialway] += 1

        # Build the lift list in the format "3x Tiefenbachbahn, 2x Schwarze Schneid, 1x Mutkogl"
        lift_parts = []
        for aerialway, count in lift_counts.most_common():
            lift_parts.append(f"{count}x {aerialway.name}")

        lifts_string = ", ".join(lift_parts)

        # Create the marked content
        marked_content = f"🎿 {lifts_string} - tracked by SlopeLog.com 🎿"

        # Remove any existing SlopeLog content from the description using regex
        import re
        pattern = r'🎿.*?- tracked by SlopeLog.com 🎿'
        cleaned_description = re.sub(pattern, '', existing_description, flags=re.DOTALL).strip()

        # Combine: user content + our content
        if cleaned_description:
            final_description = f"{marked_content}\n\n{cleaned_description}"
        else:
            final_description = marked_content

        self.profiler.end_operation('generate_strava_description')
        logger.info(f"Generated Strava description for activity {activity_instance.id}")
        return final_description

    def update_strava_description(self, activity_instance: Activity) -> bool:
        """
        Update the Strava activity description with lift ride information.
        Only updates if user has opted in for Strava write access.
        """
        self.profiler.start_operation('update_strava_description')

        try:
            # Check if user has opted in for Strava write access
            profile = UserProfile.objects.get(user=activity_instance.user)
            if not profile.opt_in_strava_write:
                logger.debug(f"User {activity_instance.user.username} has not opted in for Strava write access")
                self.profiler.end_operation('update_strava_description')
                return False

            # Load the current activity from Strava to get existing description
            strava_activity = load_activity(activity_instance.user, activity_instance.strava_id)
            existing_description = strava_activity.description or ""

            # Generate new description
            new_description = self.generate_strava_description(activity_instance, existing_description)

            # Update on Strava
            success = update_activity_description(
                activity_instance.user,
                activity_instance.strava_id,
                new_description
            )

            self.profiler.end_operation('update_strava_description')
            return success

        except StravaWritePermissionError:
            # Token lacks activity:write — reset user to read-only and propagate
            profile.opt_in_strava_write = False
            profile.save(update_fields=['opt_in_strava_write'])
            logger.warning(
                f"Reset opt_in_strava_write=False for user {activity_instance.user.username}: "
                "Strava token is missing activity:write_permission"
            )
            self.profiler.end_operation('update_strava_description')
            raise
        except UserProfile.DoesNotExist:
            logger.warning(f"No profile found for user {activity_instance.user.username}")
            self.profiler.end_operation('update_strava_description')
            return False
        except Exception as e:
            logger.error(f"Error updating Strava description for activity {activity_instance.id}: {e}", exc_info=True)
            self.profiler.end_operation('update_strava_description')
            return False

    def send_activity_summary_email(self, activity_instance: Activity) -> bool:
        """
        Send activity summary email to user if they have opted in.
        Only sends if user has opt_in_summary_email = True in their profile.

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        self.profiler.start_operation('send_activity_summary_email')

        try:
            # Check if user has opted in for summary emails
            profile = UserProfile.objects.get(user=activity_instance.user)
            if not profile.opt_in_summary_email:
                logger.debug(f"User {activity_instance.user.username} has not opted in for summary emails")
                self.profiler.end_operation('send_activity_summary_email')
                return False

            # Check if user has an email address
            if not activity_instance.user.email:
                logger.warning(f"User {activity_instance.user.username} has no email address")
                self.profiler.end_operation('send_activity_summary_email')
                return False

            # Gather activity data for email
            from django.template.loader import render_to_string
            from django.core.mail import send_mail
            from django.conf import settings

            # Get lift rides (uphill only for summary)
            lift_rides = LiftRide.objects.filter(
                lap__activity=activity_instance,
                uphill=True
            ).select_related('aerialway', 'lap').order_by('timestamp')

            # Get piste rides (>500m only for summary)
            piste_rides = PisteRide.objects.filter(
                lap__activity=activity_instance
            ).select_related('piste', 'piste__way', 'lap').order_by('lap__lap_index', 'timestamp')

            # Calculate length in meters and filter to >500m
            piste_rides_filtered = []
            for piste_ride in piste_rides:
                if piste_ride.piste.geom:
                    # Transform to Web Mercator (EPSG:3857) for accurate length calculation
                    geom_meters = piste_ride.piste.geom.transform(3857, clone=True)
                    length_meters = int(geom_meters.length)
                    if length_meters > 500:
                        piste_ride.length_meters = length_meters
                        piste_rides_filtered.append(piste_ride)

            # Get badges earned for this activity
            from activities.models import ActivityBadge
            badges = ActivityBadge.objects.filter(
                activity=activity_instance
            ).select_related('badge')

            # Get completeness data
            completeness_data = None
            try:
                from activities.utils.completeness import calculate_activity_completeness
                completeness_data = calculate_activity_completeness(activity_instance)
            except Exception as e:
                logger.warning(f"Could not get completeness data for activity {activity_instance.id}: {e}")

            # Build email context
            # Get site URL from settings or construct from ALLOWED_HOSTS
            site_url = getattr(settings, 'SITE_URL', None)
            if not site_url:
                allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
                if allowed_hosts and allowed_hosts[0]:
                    site_url = f"https://{allowed_hosts[0]}"
                else:
                    site_url = "https://www.slopelog.com"  # fallback

            context = {
                'activity': activity_instance,
                'device_name': activity_instance.device_name,
                'has_season_pass': activity_instance.has_valid_season_pass(),
                'total_descent': round(activity_instance.total_descent or 0),
                'total_distance_km': round(activity_instance.total_distance / 1000, 2) if activity_instance.total_distance else 0,
                'num_lift_rides': activity_instance.num_lift_rides or 0,
                'total_elapsed_time': activity_instance.total_elapsed_time,
                'total_ascent': round(activity_instance.total_ascent or 0),
                'avg_speed': round(activity_instance.avg_speed * 3.6, 1) if activity_instance.avg_speed else None,
                'max_speed': round(activity_instance.max_speed * 3.6, 1) if activity_instance.max_speed else None,
                'lift_rides': lift_rides,
                'piste_rides': piste_rides_filtered,
                'badges': badges,
                'completeness_percentage': round(completeness_data.get('daily_completion_percentage', 0)) if completeness_data else None,
                'lifts_used_today': completeness_data.get('lifts_used_today', 0) if completeness_data else 0,
                'total_lifts_available': completeness_data.get('total_lifts_available', 0) if completeness_data else 0,
                'new_lifts_discovered': completeness_data.get('new_lifts_discovered', 0) if completeness_data else 0,
                'activity_url': f"{site_url}/activities/{activity_instance.id}/",
                'settings_url': f"{site_url}/account/profile/",
            }

            # Render email template
            html_message = render_to_string('emails/activity_summary.html', context)

            # Create plain text version (simple fallback)
            plain_message = f"""
{activity_instance.name}

Your ski activity at {activity_instance.ski_area.name} on {activity_instance.start_time.strftime('%B %d, %Y')}

Key Stats:
- Descent: {context['total_descent']}m
- Distance: {context['total_distance_km']}km
- Lift Rides: {context['num_lift_rides']}
- Duration: {context['total_elapsed_time']}

View full details: {context['activity_url']}

---
You're receiving this email because you opted in to activity summaries.
Manage your preferences: {context['settings_url']}
            """.strip()

            # Send email
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
            if not from_email:
                logger.error("DEFAULT_FROM_EMAIL is not set in settings. Cannot send activity summary.")
                self.profiler.end_operation('send_activity_summary_email')
                return False

            send_mail(
                subject=f"🎿 {activity_instance.name} - Activity Summary",
                message=plain_message,
                from_email=from_email,
                recipient_list=[activity_instance.user.email],
                html_message=html_message,
                fail_silently=False,
            )

            logger.info(f"Activity summary email sent to {activity_instance.user.email} for activity {activity_instance.id}")
            self.profiler.end_operation('send_activity_summary_email')
            return True

        except UserProfile.DoesNotExist:
            logger.warning(f"No profile found for user {activity_instance.user.username}")
            self.profiler.end_operation('send_activity_summary_email')
            return False
        except Exception as e:
            logger.error(f"Error sending activity summary email for activity {activity_instance.id}: {e}", exc_info=True, stack_info=True)
            self.profiler.end_operation('send_activity_summary_email')
            return False

    def _finalize_activity_processing(self, activity_instance: Activity, activity_streams: Dict, was_created: bool = False) -> None:
        """Finalize activity processing with calculations and badges.

        Args:
            activity_instance: The activity to finalize
            activity_streams: Activity stream data
            was_created: True if this is a newly created activity (not a reprocessing)
        """
        self.profiler.start_operation('finalize_activity_processing')

        # Calculate vertical metrics
        self.calc_vertical_activity(activity_instance, activity_streams["altitude"].data, update=True)

        # Calculate geometry
        self.calc_line_geom(activity_instance, activity_streams["latlng"].data)

        # Calculate ridden segments
        self.calc_ridden_segments(activity_instance)

        # Process piste rides
        self._process_piste_rides(activity_instance, activity_streams)

        # Assign cost
        self.assign_cost(activity_instance)

        # Update activity statistics
        activity_instance.num_laps = activity_instance.laps.count()
        activity_instance.num_lift_rides = activity_instance.laps.aggregate(
            total_lift_rides=Count('lift_rides')
        )['total_lift_rides']
        activity_instance.processed_on = timezone.now()
        activity_instance.save()

        self._calculate_completeness(activity_instance)

        # Assign badges
        assign_badges(activity_instance)
        logger.info(f"Assigned badges to activity {activity_instance.id}")

        # Update Strava description if user has opted in
        self.update_strava_description(activity_instance)

        # Send activity summary email if user has opted in (only on initial creation)
        if was_created:
            self.send_activity_summary_email(activity_instance)
            logger.info(f"Sent activity summary email for newly created activity {activity_instance.id}")
        else:
            logger.debug(f"Skipping activity summary email for reprocessed activity {activity_instance.id}")

        self.profiler.end_operation('finalize_activity_processing')

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of all profiling data."""
        return self.profiler.get_summary()

    def log_performance_summary(self) -> None:
        """Log a summary of all profiling data."""
        self.profiler.log_summary()
        self.profiler.persist_stats()
        if self.config.NOTIFY_ADMIN:
            self.profiler.notify_admin()


# Minimal compatibility functions for existing application code
@transaction.atomic
def sync_strava_activity(user: User, activity_id: str, update: bool = False) -> Optional[Activity]:
    """Sync a single Strava activity - compatibility function for existing application code."""
    if Activity.objects.filter(strava_id=activity_id).exists() and not update:
        logger.info(f"Strava activity {activity_id} already exists in the database.")
        return Activity.objects.get(strava_id=activity_id)
    parser = ActivityParser()
    result = parser.sync_strava_activity(user, activity_id, update)
    # Log performance summary for the main operation
    parser.log_performance_summary()
    return result


@transaction.atomic
def calc_ridden_segments(activity: Activity) -> None:
    """Calculate ridden segments - compatibility function for existing application code."""
    parser = ActivityParser()
    parser.calc_ridden_segments(activity)




