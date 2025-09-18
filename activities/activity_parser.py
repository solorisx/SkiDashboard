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
from activities.models import Activity, Lap, Record, LiftRide, ActivityPisteSegment
from osm.models import Node, Way, Aerialway, SkiArea, Station, SkiAreaBoundary, PisteSegment
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



from .strava_interface import load_activities, load_activity, load_activity_streams, load_activity_laps

# Get an instance of a logger
logger = logging.getLogger('core')


@dataclass
class ActivityParserConfig:
    """Configuration settings for the activity parser."""
    DEFAULT_MAX_DISTANCE: int = 250
    DEFAULT_BUFFER_METERS: int = 50
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

    def end_operation(self, operation_name: str) -> float:
        """End timing an operation and return the duration."""
        if operation_name not in self.current_operations:
            logger.warning(f"Attempted to end operation '{operation_name}' that was never started")
            return 0.0

        start_time = self.current_operations.pop(operation_name)
        duration = time.time() - start_time
        self.timings[operation_name].append(duration)
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
        if not tz_string:
            return timezone.make_aware(dt)

        # Extract timezone name from Strava format like "(GMT+01:00) Europe/Zurich"
        # Look for the part after ") " which should be the timezone name
        match = re.search(r'\)\s+(.+)$', tz_string)
        if match:
            tz_name = match.group(1)
        else:
            # Fallback: use the original string
            tz_name = tz_string

        try:
            tz = pytz.timezone(tz_name)
            self.timezone = tz
            return tz.localize(dt)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone '{tz_name}' from Strava timezone '{tz_string}', using UTC")
            self.timezone = pytz.UTC
            return timezone.make_aware(dt)

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
            if direction == "valley":
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

        for i, lap_data_item in enumerate(lap_data):
            Lap.objects.update_or_create(lap_index=i+1, activity=activity, defaults=lap_data_item)

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

        buffer_width = self.config.DEFAULT_BUFFER_METERS / 40000000 * 360  # roughly 50 meters
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

            activity = load_activity(user, activity_id)
            if not activity:
                logger.error(f"Strava activity {activity_id} not found", exc_info=True, stack_info=True)
                raise ValueError(f"Strava activity {activity_id} not found")

            if not activity.type == 'AlpineSki':
                logger.warning(f"Strava activity {activity_id} is not an AlpineSki activity.")
                return None

            activity_streams = load_activity_streams(user, activity_id)

            lat, lon = activity_streams["latlng"].data[0]
            start_point = Point(lon, lat)
            activity_laps = load_activity_laps(user, activity_id)
            start_lift = self.get_closest_aerialway(start_point, in_ski_area=True, max_distance=2000)
            # if start_lift:
            #     logger.debug(f"Found start lift: {start_lift.name}")
            #     skiarea = SkiArea.objects.filter(ways=start_lift.way).first()
            # else:
            #     skiarea = None
            #     logger.warning(f"No start lift found for activity: {activity_id}")

            # try:
            #     boundary_time = time.time()
            #     ski_area_boundary = get_ski_area_boundary(start_point)
            #     logger.debug(f"Found ski area boundary: {ski_area_boundary} in {time.time() - boundary_time:.4f} seconds")
            # except Exception as e:
            #     logger.error(f"Error getting ski area boundary: {e}")
            #     ski_area_boundary = None

            ski_area = self.get_ski_area(start_point)

            if not ski_area:
                logger.warning(f"No ski area found for activity: {activity_id}, searching relations")
                if start_lift:
                    ski_area = SkiArea.objects.filter(ways=start_lift.way).first()
                    logger.debug(f"Found ski area from relation: {ski_area}")
                else:
                    logger.warning(f"No start lift found for activity: {activity_id}")

            logger.debug(f"Loaded Strava activity: {activity_id}")

            #skiarea_main = ski_area_boundary if ski_area_boundary else skiarea if skiarea else None

            activity_data = {
                "name": activity.name,
                "type": activity.type,
                "start_time": self._make_timezone_aware(activity.start_date_local, activity.timezone),
                "timestamp": self._make_timezone_aware(activity.start_date_local, activity.timezone),
                "summary_polyline": activity.map.summary_polyline,
                "polyline": None,               # TODO: would separate API call, probably summary polyline is enough
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
                "ski_area": ski_area if ski_area else None,
                # "ski_area_boundary": ski_area_boundary if ski_area_boundary else None,
                # "ski_area_main": skiarea_main
            }

            activity_instance, created = Activity.objects.update_or_create(strava_id=activity_id, defaults=activity_data)
            self.activity = activity_instance
            logger.info(f'{"Created" if created else "Updated"} Activity: {activity_instance.id}')

            if not created:
                activity_instance.version += 1
                activity_instance.laps.all().delete()
                logger.info(f"Deleted existing laps for Activity: {activity_instance.id}")

            activity_start_time = activity_instance.start_time
            logger.info(f"Activity start time: {activity_start_time}")
            logger.info(f"timezone: {activity.timezone}, localtime: {activity.start_date_local}")
            logger.info(f"tz: {self.timezone}")
            for lap in activity_laps:
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
                    "start_position": Point(activity_streams["latlng"].data[lap.start_index+5][1], activity_streams["latlng"].data[lap.start_index+5][0]),
                    "end_position": Point(activity_streams["latlng"].data[lap.end_index-5][1], activity_streams["latlng"].data[lap.end_index-5][0]),
                    "end_time": activity_start_time + timedelta(seconds=activity_streams["time"].data[lap.end_index]),
                }
                lap_instance, created = Lap.objects.update_or_create(lap_index=lap.lap_index, activity=activity_instance, defaults=lap_data)

                logger.debug(f"Lap data: {lap_data}")
                logger.info(f'{"Created" if created else "Updated"} Lap: {lap_instance.lap_index}')

            logger.debug(f"Number of laps: {activity_instance.laps.count()}")
            if activity_instance.laps.count() == 1 or \
                (activity_instance.laps.count() > 30 and \
                activity_instance.timestamp < datetime(year=2019, month=12, day=31)):
            # no auto pause used or old activities with bad lap data
                activity_instance.laps.all().delete()
                self.split_activity(activity_instance, activity_streams)

            for lap in activity_instance.laps.all():
                logger.debug(f"Processing Lap: {lap.lap_index}")
                logger.debug(f"Start Position (Lap): {self.get_osm_url(lap.start_position)} at {lap.start_time}")
                logger.debug(f"End Position (Lap): {self.get_osm_url(lap.end_position)} at {lap.end_time}")
                lift_end_pos = lap.start_position
                prev_lap = Lap.objects.filter(activity=activity_instance, lap_index=lap.lap_index-1).first()
                if prev_lap:
                    lift_start_pos = prev_lap.end_position
                    lift_start_time = prev_lap.end_time
                else:
                    lift_start_pos = None
                    lift_start_time = lap.start_time
                #lift_start_pos = Lap.objects.filter(activity=activity_instance, lap_index=lap.lap_index-1).first().end_position if lap.lap_index > 1 else None
                lift_rides = self.get_aerialways(lift_start_pos, lift_end_pos, start_activity=activity_instance.start_position)
                for (lift_ride, uphill) in lift_rides:
                    logger.debug(lift_rides)

                    logger.debug(f"Found lift ride: {lift_ride if lift_ride else 'unnamed'}")
                    logger.debug(f"Uphill: {uphill}")
                    logger.debug(f"lap: {lap}, lift_ride: {lift_ride}, uphill: {uphill}, timestamp: {lift_start_time}")
                    lift_ride = self.apply_exceptions(lift_ride)
                    lift, _ = LiftRide.objects.update_or_create(lap=lap, aerialway=lift_ride, uphill=uphill if True else False, timestamp=lift_start_time)
                    lift_start_time = lift_start_time + timedelta(minutes=lift.aerialway.aerialway_duration if lift.aerialway.aerialway_duration else 1)
                    logger.info(f"Created LiftRide for Lap: {lap.lap_index} with lift {lift_ride.name if lift_ride else 'unnamed'}")

            # Complete the activity processing
            self.calc_vertical_activity(activity_instance, activity_streams["altitude"].data, update=True)
            self.calc_line_geom(activity_instance, activity_streams["latlng"].data)
            self.calc_ridden_segments(activity_instance)
            self.assign_cost(activity_instance)

            activity_instance.num_laps = activity_instance.laps.count()
            activity_instance.num_lift_rides = activity_instance.laps.aggregate(total_lift_rides=Count('lift_rides'))['total_lift_rides']
            activity_instance.processed_on = timezone.now()
            activity_instance.processing_time = timedelta(seconds=time.time() - start_time)
            activity_instance.save()

            assign_badges(activity_instance)
            logger.info(f"Assigned badges to activity {activity_instance.id}")

            logger.info(f"Finished parsing Strava activity: {activity_id} in {time.time() - start_time:.4f} seconds")

            return activity_instance

        except Exception as e:
            logger.error(f"Error parsing Strava activity {activity_id}: {str(e)}", exc_info=True, stack_info=True)
            raise

    def _finalize_activity_processing(self, activity_instance: Activity, activity_streams: Dict) -> None:
        """Finalize activity processing with calculations and badges."""
        self.profiler.start_operation('finalize_activity_processing')

        # Calculate vertical metrics
        self.calc_vertical_activity(activity_instance, activity_streams["altitude"].data, update=True)

        # Calculate geometry
        self.calc_line_geom(activity_instance, activity_streams["latlng"].data)

        # Calculate ridden segments
        self.calc_ridden_segments(activity_instance)

        # Assign cost
        self.assign_cost(activity_instance)

        # Update activity statistics
        activity_instance.num_laps = activity_instance.laps.count()
        activity_instance.num_lift_rides = activity_instance.laps.aggregate(
            total_lift_rides=Count('lift_rides')
        )['total_lift_rides']
        activity_instance.processed_on = timezone.now()
        activity_instance.save()

        self.profiler.start_operation('calculate_ski_area_completeness')
        completeness.calculate_ski_area_completeness(user=activity_instance.user, ski_area=activity_instance.ski_area, force_recalc=True)
        self.profiler.end_operation('calculate_ski_area_completeness')

        # Assign badges
        assign_badges(activity_instance)
        logger.info(f"Assigned badges to activity {activity_instance.id}")
        
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




