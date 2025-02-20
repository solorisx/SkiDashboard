import logging
import time
from datetime import timedelta
from fitparse import FitFile
from SkiingDashboardApp.activity_models import Activity, Lap, Record, LiftRide
from SkiingDashboardApp.osm_models import Node, Way, Aerialway, SkiArea
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from .strava_interface import load_activity, load_activity_streams, load_activity_laps

# Get an instance of a logger
logger = logging.getLogger('SkiingDashboard')

def extract_data(message, model_fields):
    """
    Extract data from a FIT message based on the fields available in the corresponding Django model.
    """
    start_time = time.time()
    data = {
        field: message.get_value(field)
        for field in model_fields
        if message.get_value(field) is not None
    }
    duration = time.time() - start_time
    logger.debug(f"Extracted data: {data} (took {duration:.4f} seconds)")
    return data

def create_point(lat_field, lon_field, data):
    start_time = time.time()
    if lat_field in data and lon_field in data:
        lon = data[lon_field] / 11930465
        lat = data[lat_field] / 11930465
        point = Point(lon, lat)
        duration = time.time() - start_time
        logger.debug(f"Created point: {point} (took {duration:.4f} seconds)")
        return point
    return None

def get_closest_aerialways(point: Point, in_ski_area=False, max_distance=250, bottom_only=False, top_only=False):

    start_time = time.time()
    point.srid = 4326
    
    aerialways = Aerialway.objects.all()
    
    if in_ski_area:
        aerialways = aerialways.filter(way__ski_areas__isnull=False)

    if bottom_only and top_only:
        raise ValueError("Cannot filter for bottom and top stations at the same time")
    
    # TODO add filter for bottom/top stations only
    
    aerialways = aerialways.annotate(distance=Distance("station_nodes__geom", point))
    
    closest_aerialways = (
        aerialways.filter(distance__lte=max_distance)
        .order_by("distance")
    )
    
    duration = time.time() - start_time
    if closest_aerialways:
        logger.debug(f"Found closest aerialways: {closest_aerialways} (took {duration:.4f} seconds)")
    else:
        logger.debug(f"No closest aerialway found (took {duration:.4f} seconds)")
    
    return closest_aerialways


def get_closest_aerialway(point: Point, in_ski_area=False, max_distance=250, bottom_only=False, top_only=False):
    return get_closest_aerialways(point, in_ski_area, max_distance, bottom_only, top_only).first()

def find_direct_lift(start: Point, end: Point):
    """Finds a direct lift (Aerialway) connecting two points."""
    
    start_stations = get_closest_aerialways(start)
    end_stations = get_closest_aerialways(end)

    direct_lift = Aerialway.objects.filter(
        station_nodes__in=start_stations
    ).filter(
        station_nodes__in=end_stations
    ).distinct().first()  # Get the first matching aerialway (or None if no match)

    return direct_lift


def get_aerialways(start: Point, end: Point = None):
    
    # TODO: improve this function
    # get set of aerialways, if multiple then check for start / end points

    if start is None or end is None:
        if start is None:
            aerialway = get_closest_aerialway(end)
        if end is None:
            aerialway = get_closest_aerialway(start)
        if aerialway:
            return [aerialway]
        else:
            return []
        
    direct_lift = find_direct_lift(start, end)
    if direct_lift:
        return [direct_lift]

    # Find all nearby stations for start and end
    max_distance = 250
    start_stations = list(Node.objects.annotate(distance=Distance("geom", start)).filter(distance__lte=max_distance))
    end_stations = list(Node.objects.annotate(distance=Distance("geom", end)).filter(distance__lte=max_distance))

    if not start_stations or not end_stations:
        return []  # No valid stations found

    # Build Graph: Nodes (Stations), Edges (Aerialways + Walking connections)
    graph = {}

    # Add direct lift connections
    for aerialway in Aerialway.objects.prefetch_related("station_nodes"):
        stations = list(aerialway.station_nodes.all())
        for i in range(len(stations) - 1):
            station_a, station_b = stations[i], stations[i + 1]
            distance = station_a.geom.distance(station_b.geom)
            graph.setdefault(station_a, []).append((distance, station_b, aerialway))
            graph.setdefault(station_b, []).append((distance, station_a, aerialway))

    # Add walking connections within max_distance
    stations = list(Node.objects.all())
    for i in range(len(stations)):
        for j in range(i + 1, len(stations)):
            station_a, station_b = stations[i], stations[j]
            distance = station_a.geom.distance(station_b.geom)
            if distance <= max_distance:
                graph.setdefault(station_a, []).append((distance, station_b, None))  # No lift, just walking
                graph.setdefault(station_b, []).append((distance, station_a, None))

    # Run Dijkstra’s Algorithm allowing multiple start & end nodes
    def dijkstra(start_nodes, end_nodes):
        """Finds the shortest path between any start node and any end node."""
        queue = [(0, start_node, []) for start_node in start_nodes]  # (distance, current_node, path)
        visited = set()
        shortest_path = None

        while queue:
            dist, current, path = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            path = path + [current]

            if current in end_nodes:
                return path  # Return path if any destination is reached

            for weight, neighbor, aerialway in graph.get(current, []):
                if neighbor not in visited:
                    heapq.heappush(queue, (dist + weight, neighbor, path))

        return []  # No path found

    # Get the shortest station path from multiple start and end stations
    station_path = dijkstra(start_stations, end_stations)

    # Extract aerialways from station path
    aerialway_path = []
    for i in range(len(station_path) - 1):
        station_a, station_b = station_path[i], station_path[i + 1]
        connection = next(
            (aerialway for _, neighbor, aerialway in graph[station_a] if neighbor == station_b and aerialway),
            None
        )
        if connection and connection not in aerialway_path:
            aerialway_path.append(connection)

    return aerialway_path

def parse_fit_file(file_path):
    start_time = time.time()
    logger.info(f"Starting to parse FIT file: {file_path}")
    fitfile = FitFile(file_path)

    activity_data = None
    laps = []
    current_lap_records = []
    activity_fields = [f.name for f in Activity._meta.get_fields() if f.name != "laps"]
    lap_fields = [f.name for f in Lap._meta.get_fields() if f.name != "activity"]
    record_fields = [f.name for f in Record._meta.get_fields() if f.name != "lap"]

    # Process each message in the FIT file
    for message in fitfile.get_messages():
        if message.name == "record":
            record_data = extract_data(message, record_fields)
            record_data_pos = extract_data(message, ["position_lat", "position_long"])
            record_data["position"] = create_point(
                "position_lat", "position_long", record_data_pos
            )
            current_lap_records.append(record_data)
            logger.debug(f"Processed record message: {record_data}")

        elif message.name == "lap":
            current_lap_data = extract_data(message, lap_fields)
            current_lap_data_pos = extract_data(message, ["start_position_lat", "start_position_long", "end_position_lat", "end_position_long"])
            current_lap_data['total_elapsed_time'] = timedelta(seconds=current_lap_data['total_elapsed_time'])
            current_lap_data['total_timer_time'] = timedelta(seconds=current_lap_data['total_timer_time'])
            current_lap_data["start_position"] = create_point(
                "start_position_lat", "start_position_long", current_lap_data_pos
            )
            current_lap_data["end_position"] = create_point(
                "end_position_lat", "end_position_long", current_lap_data_pos
            )
            current_lap_data["records"] = current_lap_records
            laps.append(current_lap_data)
            current_lap_records = []
            current_lap_data_pos = []
            logger.debug(f"Processed lap message: {current_lap_data}")

        elif message.name == "session":
            activity_data = extract_data(message, activity_fields)
            activity_data_pos = extract_data(message, ["start_position_lat", "start_position_long"])
            activity_data['total_elapsed_time'] = timedelta(seconds=activity_data['total_elapsed_time'])
            activity_data['total_timer_time'] = timedelta(seconds=activity_data['total_timer_time'])
            activity_data['start_position'] = create_point(
                "start_position_lat", "start_position_long", activity_data_pos
            )
            logger.debug(f"Processed session message: {activity_data}")

        logger.debug(f"Processed message: {message.name}")

    if not activity_data:
        logger.error("No session found in FIT file.")
        raise ValueError("No session found in FIT file.")

    # Create Activity instance
    activity = Activity.objects.create(**activity_data)
    logger.info(f"Created Activity: {activity.id}")

    # Create Lap and Record instances
    for lap_data in laps:
        # Remove the separate latitude and longitude fields
        lap_data.pop("start_position_lat", None)
        lap_data.pop("start_position_long", None)
        lap_data.pop("end_position_lat", None)
        lap_data.pop("end_position_long", None)

        records = lap_data.pop("records")

        lap = Lap.objects.create(activity=activity, **lap_data)
        logger.info(f"Created Lap: {lap.id}")

        lift_ride = get_closest_aerialway(lap.start_position)

        if lift_ride:
            LiftRide.objects.create(
                lap=lap, aerialway=lift_ride, timestamp=lap.start_time
            )
            logger.info(f"Created LiftRide for Lap: {lap.id}")

        for record_data in records:
            # Remove the separate latitude and longitude fields
            record_data.pop("position_lat", None)
            record_data.pop("position_long", None)

            Record.objects.create(lap=lap, **record_data)
            logger.debug(f"Created Record for Lap: {lap.id}")

        logger.debug(f"Processed lap: {lap.id}")

    total_duration = time.time() - start_time
    logger.info(f"Finished parsing FIT file: {file_path} in {total_duration:.4f} seconds")

def parse_strava_activity(user, activity_id, update=False):
    start_time = time.time()
    logger.info(f"Starting to parse Strava activity: {activity_id}")
    
    if not update and Activity.objects.filter(strava_id=activity_id).exists():
        logger.warning(f"Strava activity {activity_id} already exists in the database.")
        return
    
    activity = load_activity(user, activity_id)
    activity_streams = load_activity_streams(user, activity_id)
    lat, lon = activity_streams["latlng"].data[0]
    start_point = Point(lon, lat)
    activity_laps = load_activity_laps(user, activity_id)
    skiarea = SkiArea.objects.filter(ways=get_closest_aerialway(start_point, in_ski_area=True, max_distance=5000).way).first()
    logger.debug(f"Loaded Strava activity: {activity_id}")

    activity_data = {
        "name": activity.name,
        "type": activity.type,
        "start_time": activity.start_date_local, # TODO: add timezone
        "timestamp": activity.start_date_local, # TODO: add timezone
        "total_elapsed_time": timedelta(seconds=activity.elapsed_time),
        "total_timer_time": timedelta(seconds=activity.moving_time),
        "total_distance": activity.distance,
        "total_ascent": activity.total_elevation_gain,
        # TODO: get total_descent from streams
        "avg_speed": activity.average_speed,
        "max_speed": activity.max_speed,
        "total_calories": activity.calories,
        "avg_heart_rate": activity.average_heartrate,
        "max_heart_rate": activity.max_heartrate,
        "user": user,
        "start_position": start_point,
        "ski_area": skiarea,
    }

    activity_instance, created = Activity.objects.update_or_create(strava_id=activity_id, defaults=activity_data)
    logger.info(f'{"Created" if created else "Updated"} Activity: {activity_instance.id}')

    if not created:
        activity_instance.laps.all().delete()
        logger.info(f"Deleted existing laps for Activity: {activity_instance.id}")

    for lap in activity_laps:
        lap_data = {
            "start_time": lap.start_date_local, # TODO: add timezone
            "timestamp": lap.start_date_local, # TODO: add timezone
            "total_elapsed_time": timedelta(seconds=lap.elapsed_time),
            "total_timer_time": timedelta(seconds=lap.moving_time),
            "total_distance": lap.distance,
            "total_ascent": lap.total_elevation_gain,
            # TODO: get total_descent from streams
            "avg_speed": lap.average_speed,
            "max_speed": lap.max_speed,
            "avg_heart_rate": lap.average_heartrate,
            "max_heart_rate": lap.max_heartrate,
            "start_position": Point(activity_streams["latlng"].data[lap.start_index][1], activity_streams["latlng"].data[lap.start_index][0]),
            "end_position": Point(activity_streams["latlng"].data[lap.end_index][1], activity_streams["latlng"].data[lap.end_index][0]),
        }
        lap_instance, created = Lap.objects.update_or_create(lap_index=lap.lap_index, activity=activity_instance, defaults=lap_data)
        logger.info(f'{"Created" if created else "Updated"} Lap: {lap_instance.lap_index}')

    for lap in activity_instance.laps.all():
        lift_end_pos = lap.start_position
        lift_start_pos = Lap.objects.filter(activity=activity_instance, lap_index=lap.lap_index-1).first().end_position if lap.lap_index > 1 else None
        lift_rides = get_aerialways(lift_start_pos, lift_end_pos)
        for lift_ride in lift_rides:
            LiftRide.objects.create(lap=lap, aerialway=lift_ride, timestamp=lap.start_time)
            logger.info(f"Created LiftRide for Lap: {lap_instance.lap_index}")

    # TODO: 
    #   - create line geom



