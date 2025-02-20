import heapq
import logging
import time
from datetime import timedelta
from fitparse import FitFile
from SkiingDashboardApp.activity_models import Activity, Lap, Record, LiftRide
from SkiingDashboardApp.osm_models import Node, Way, Aerialway, SkiArea, Station
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.db.models import F
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Exists, OuterRef


from .strava_interface import load_activity, load_activity_streams, load_activity_laps

# Get an instance of a logger
logger = logging.getLogger('SkiingDashboard')

def get_osm_url(point):
    return f"https://www.openstreetmap.org/?mlat={point.y}&mlon={point.x}#map=17/{point.y}/{point.x}"

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
    
    aerialways = aerialways.annotate(distance=Distance("station_nodes__node__geom", point))
    
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


def get_closest_stations(point: Point, max_distance=250, bottom_only=False, top_only=False):

    start_time = time.time()
    point.srid = 4326
    
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
    
    duration = time.time() - start_time
    if closest_stations:
        logger.debug(f"Found closest aerialways: {closest_stations.all()} (took {duration:.4f} seconds)")
    else:
        logger.debug(f"No closest aerialway found (took {duration:.4f} seconds)")
    
    return closest_stations


def get_closest_aerialway(point: Point, in_ski_area=False, max_distance=250, bottom_only=False, top_only=False):
    return get_closest_aerialways(point, in_ski_area, max_distance, bottom_only, top_only).first()


def find_direct_lift(start: Point, end: Point):
    """Finds a direct lift (Aerialway) connecting two points."""
    logger.debug(f"Finding direct lift between {start} and {end}")
    logger.debug(f"Start OSM URL: {get_osm_url(start)}")
    logger.debug(f"End OSM URL: {get_osm_url(end)}")

    start_stations = get_closest_stations(start)
    end_stations = get_closest_stations(end)

    # Get aerialways that have a start station
    aerialways_with_start = Aerialway.objects.filter(
        station_nodes__in=start_stations
    ).distinct()

    # Get aerialways that have an end station
    direct_lift = aerialways_with_start.filter(
        Exists(
            Station.objects.filter(
                aerialways=OuterRef("pk"),
                id__in=end_stations.values_list("id", flat=True)  # Ensure correct filtering
            )
        )
    ).first()  # Fetch the first matching aerialway

    return direct_lift


def build_lift_graph(start: Point, max_area: int = 20_000, max_distance: int = 500):
    """Builds a graph of aerialways and walking connections within 200 km of the start position."""
    startTime = time.time()
    logger.info("Building lift graph")   
    
    graph = {}

    # **Filter stations within 20km of start**
    logger.info(f"Filtering stations within {max_area}m of start position")
    nearby_stations = Station.objects.annotate(
        distance=Distance("node__geom", start)
    ).filter(distance__lte=max_area)

    for station in nearby_stations:
        logger.debug(f"Station: {station.name}, OSM ID {station.node.osm_id} ({station.distance}m)")

    # **Filter aerialways whose stations are within 200km**
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

    # **Add walking connections within max_distance**
    logger.info("Adding walking connections")
    for station in nearby_stations:
        nearby_walkable_stations = (
            nearby_stations.annotate(distance=Distance(F("node__geom"), station.node.geom))
            .filter(distance__lte=max_distance)
            .exclude(id=station.id)  # Exclude itself
        )
        for nearby_station in nearby_walkable_stations:
            distance = station.node.geom.distance(nearby_station.node.geom)
            graph.setdefault(station, []).append((distance, nearby_station, None))
            graph.setdefault(nearby_station, []).append((distance, station, None))  # Add both directions

    duration = time.time() - startTime
    logger.info(f"Built lift graph in {duration:.4f} seconds")
    return graph

def dijkstra(start_nodes, end_nodes, graph):
    """Finds the shortest path between any start node and any end node."""
    logger.info("Running Dijkstra's algorithm")
    startTime = time.time()
    queue = [(0, id(start_node), start_node, []) for start_node in start_nodes]  # (distance, current_node, path)
    visited = set()
    path = None

    while queue:
        dist, _, current, path = heapq.heappop(queue)  # Pop the node with the smallest distance, then tie break by id
        if current in visited:
            continue
        visited.add(current)
        path = path + [current]

        if current in end_nodes:
            logger.info(f"Found path in {time.time() - startTime:.4f} seconds")
            return path  # Return path if any destination is reached

        for weight, neighbor, aerialway in graph.get(current, []):
            if neighbor not in visited:
                heapq.heappush(queue, (dist + weight, id(neighbor), neighbor, path))

    logger.warning("No path found in %s seconds", time.time() - startTime)
    return []  # No path found

def get_aerialways(start: Point, end: Point = None):

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
    start_stations = list(Station.objects.annotate(distance=Distance("node__geom", start)).filter(distance__lte=max_distance))
    end_stations = list(Station.objects.annotate(distance=Distance("node__geom", end)).filter(distance__lte=max_distance))

    if not start_stations or not end_stations:
        return []  # No valid stations found

    graph = build_lift_graph(start)

    # Get the shortest station path from multiple start and end stations
    station_path = dijkstra(start_stations, end_stations, graph)

    logger.debug(f"Station path: {station_path}")
    for station in station_path:
        logger.debug(station.get_osm_url())

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
            logger.info(f"Created LiftRide for Lap: {lap.id} with lift {lift_ride.aerialway.name}")

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
            "end_position": Point(activity_streams["latlng"].data[lap.end_index-10][1], activity_streams["latlng"].data[lap.end_index-10][0]),
        }
        lap_instance, created = Lap.objects.update_or_create(lap_index=lap.lap_index, activity=activity_instance, defaults=lap_data)
        logger.info(f'{"Created" if created else "Updated"} Lap: {lap_instance.lap_index}')

    for lap in activity_instance.laps.all():
        logger.debug(f"Processing Lap: {lap.lap_index}")
        logger.debug(f"Start Position: {get_osm_url(lap.start_position)}")
        logger.debug(f"End Position: {get_osm_url(lap.end_position)}")
        lift_end_pos = lap.start_position
        lift_start_pos = Lap.objects.filter(activity=activity_instance, lap_index=lap.lap_index-1).first().end_position if lap.lap_index > 1 else None
        lift_rides = get_aerialways(lift_start_pos, lift_end_pos)
        for lift_ride in lift_rides:
            LiftRide.objects.create(lap=lap, aerialway=lift_ride, timestamp=lap.start_time)
            logger.info(f"Created LiftRide for Lap: {lap.lap_index} with lift {lift_ride.name if lift_ride else 'unnamed'}")

    logger.info(f"Finished parsing Strava activity: {activity_id} in {time.time() - start_time:.4f} seconds")
    # TODO: 
    #   - create line geom



