import heapq
import logging
import time
from datetime import timedelta, datetime
from fitparse import FitFile
import polyline
from activities.models import Activity, Lap, Record, LiftRide, ActivityPisteSegment
from osm.models import Node, Way, Aerialway, SkiArea, Station, SkiAreaBoundary, PisteSegment
from core.models import UserProfile
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, LineString
from django.db.models import F, Count
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Exists, OuterRef, Subquery
import numpy as np
from .utils import get_turning_points
from .badges import assign_badges
from cost.prices import get_daypass_price
from cost.seasonpass import has_seasonpass



from .strava_interface import load_activities, load_activity, load_activity_streams, load_activity_laps

# Get an instance of a logger
logger = logging.getLogger('core')


def apply_exceptions(aerialway: Aerialway):
    
    # replace Parsennhüttenbahn with Totalp - next to each other
    if aerialway.way.osm_id == 29258980:
        return Aerialway.objects.get(way__osm_id = 20011874)

    return aerialway

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

def get_ski_area_boundary(point, buffer=0):
    """
    Finds the ski area containing the given point.
    If buffer > 0, it expands the search to ski areas within the buffered distance.
    
    :param point: A GeoDjango Point object (longitude, latitude)
    :param buffer: Optional buffer distance in meters
    :return: SkiArea object or None if no match found
    """
    if buffer > 0:
        # Find ski areas where the point is within a buffered geometry
        ski_area_boundary = SkiAreaBoundary.objects.filter(geom__dwithin=(point, buffer)).annotate(
            distance=Distance("geom", point)
        ).order_by("distance").first()
    else:
        # Find the ski area that directly contains the point
        ski_area_boundary = SkiAreaBoundary.objects.filter(geom__contains=point).first()

    return ski_area_boundary


def get_ski_area(point, buffer=0):
    """
    Finds the ski area containing the given point.
    If buffer > 0, it expands the search to ski areas within the buffered distance.
    
    :param point: A GeoDjango Point object (longitude, latitude)
    :param buffer: Optional buffer distance in meters
    :return: SkiArea object or None if no match found
    """
    
    ski_areas = SkiArea.objects.filter(geom__isnull=False)
    
    if buffer > 0:
        # Find ski areas where the point is within a buffered geometry
        ski_area_boundary = ski_areas.filter(geom__dwithin=(point, buffer)).annotate(
            distance=Distance("geom", point)
        ).order_by("distance").first()
    else:
        # Find the ski area that directly contains the point
        ski_area_boundary = ski_areas.filter(geom__contains=point).first()

    return ski_area_boundary



def get_closest_aerialways(point: Point, in_ski_area=False, max_distance=250, bottom_only=False, top_only=False, use_nodes=False) -> list[Aerialway]:

    logger.debug(f"Finding closest aerialways to {point} (in_ski_area={in_ski_area}, max_distance={max_distance}, bottom_only={bottom_only}, top_only={top_only}, use_nodes={use_nodes})")
    logger.debug(f"OSM URL: {get_osm_url(point)}")

    start_time = time.time()
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


def get_closest_aerialway(point: Point, in_ski_area=False, max_distance=250, bottom_only=False, top_only=False, use_nodes=False):
    return get_closest_aerialways(point, in_ski_area, max_distance, bottom_only, top_only, use_nodes).first()


def find_direct_lift(start: Point, end: Point):
    """Finds a direct lift (Aerialway) connecting two points."""
    logger.debug(f"Finding direct lift between {start} and {end}")
    logger.debug(f"Start OSM URL Lift: {get_osm_url(start)}")
    logger.debug(f"End OSM URL Lift: {get_osm_url(end)}")

    start_stations = get_closest_stations(start)
    end_stations = get_closest_stations(end)

    logger.debug(f"Lift Start stations: {start_stations}")
    logger.debug(f"Lift End stations: {end_stations}")

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

    uphill = True
    if direct_lift:
        start_station = start_stations.first()
        end_station = end_stations.first()
        uphill = not (start_station.station == "top" and end_station.station == "bottom")
    logger.debug(f"Direct lift: {direct_lift}, uphill: {uphill}")
    return direct_lift, uphill


def build_lift_graph(start: Point, max_area: int = 20_000, max_distance: int = 500):
    """Builds a graph of aerialways and walking connections within 20 km of the start position."""
    startTime = time.time()
    logger.info("Building lift graph")   
    
    graph = {}

    # **Filter stations within 20km of start**
    logger.info(f"Filtering stations within {max_area}m of start position")
    nearby_stations = Station.objects.annotate(
        distance=Distance("node__geom", start)
    ).filter(distance__lte=max_area)

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

def get_aerialways(start: Point, end: Point = None) -> list[tuple[Aerialway, bool]]:
    
    uphill = True
    if start is None or end is None:
        if start is None:
            aerialway = get_closest_aerialway(end)
        if end is None:
            aerialway = get_closest_aerialway(start)
        if aerialway:
            return [(aerialway,uphill)]
        else:
            return []
        
    direct_lift, uphill = find_direct_lift(start, end)
    if direct_lift:
        return [(direct_lift, uphill)]

    # Find all nearby stations for start and end
    max_distance = 250
    start_stations = list(Station.objects.annotate(distance=Distance("node__geom", start)).filter(distance__lte=max_distance))
    end_stations = list(Station.objects.annotate(distance=Distance("node__geom", end)).filter(distance__lte=max_distance))

    if not start_stations or not end_stations:

        logger.debug("No valid stations found, trying to find aerialway without stations")

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
            lift = get_closest_aerialway(start, max_distance=100, use_nodes=True)

        if not lift:
            logger.debug("No valid stations found, trying to find aerialway with all nodes")
            lift = get_closest_aerialway(end, max_distance=100, use_nodes=True)
        
        logger.debug(lift) 
        if lift:
            return [(lift,uphill)]
        
        else:
            return []  # No valid stations found

    graph = build_lift_graph(start)
    logger.debug("graph built")

    # Get the shortest station path from multiple start and end stations
    station_path = dijkstra(start_stations, end_stations, graph)

    logger.debug(f"Station path: {station_path}")

    for station in station_path:
        logger.debug(station.get_osm_url())

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


def split_activity(activity: Activity, activity_streams: dict):
    """
    Splits a single activity into multiple laps based on the activity streams.
    """

    lap_data = []

    turning_points = get_turning_points(activity_streams["altitude"].data, prominence=100)

    diff = np.diff(activity_streams["altitude"].data)
    logger.debug(f"Number of turning points: {len(turning_points)}")
    for i, (index, direction) in enumerate(turning_points):
        logger.debug(f"Turning point {i+1}: {index}, {direction}")
        logger.debug(f"OSM URL: {get_osm_url(Point(activity_streams['latlng'].data[index][1], activity_streams['latlng'].data[index][0]))}")
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
                "total_timer_time": timedelta(activity_streams["time"].data[next] - activity_streams["time"].data[index]),
                "total_distance": activity_streams["distance"].data[next] - activity_streams["distance"].data[index],
                "total_ascent": np.sum(lap_diff[lap_diff > 0]),
                "total_descent": np.sum(np.abs(lap_diff[lap_diff < 0])),
                "start_index_stream": index,
                "end_index_stream": next,
            })

    for i, lap_data in enumerate(lap_data):
        Lap.objects.update_or_create(lap_index=i+1, activity=activity, defaults=lap_data)


def assign_cost(activity: Activity):
    skiarea = activity.ski_area
    if not skiarea:
        logger.warning(f"No ski area found for activity, no cost assisgned: {activity.id}")
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


def calc_vertical_lap(lap: Lap, altitude_stream, update=True):
    """
    Calculate the total ascent and descent for a lap.
    """
    diffs = np.diff(altitude_stream[lap.start_index_stream:lap.end_index_stream])
    lap.total_ascent = np.sum(diffs[diffs > 0])
    lap.total_descent = np.sum(np.abs(diffs[diffs < 0]))
    lap.save()


def calc_vertical_activity(activity: Activity, altitude_stream, update=True):
    """
    Calculate the total ascent and descent for an activity.
    """
    total_ascent = 0
    total_descent = 0
    for lap in activity.laps.all():
        if update:
            calc_vertical_lap(lap, altitude_stream, update=True)
        total_ascent += lap.total_ascent
        total_descent += lap.total_descent
    activity.total_ascent = total_ascent
    activity.total_descent = total_descent
    activity.save()


def calc_line_geom(activity: Activity, latlng_stream=None):
    
    if latlng_stream:
        logger.debug(f"latlng stream: {latlng_stream[0:50]}")
        swapped_coords = [(lon, lat) for lat, lon in latlng_stream]
        activity.geom = LineString(swapped_coords)
        activity.save()
        return
    
    if activity.polyline:
        coords = polyline.decode(activity.polyline)
    elif activity.summary_polyline:
        coords = polyline.decode(activity.summary_polyline)
    else:
        logger.error(f"No polyline found for activity: {activity.id}")
        return

    # Swap lat/lon to lon/lat
    swapped_coords = [(lon, lat) for lat, lon in coords]

    # Save as LineString with correct coordinate order
    activity.geom = LineString(swapped_coords, srid=4326)
    activity.save()

    logger.info(f"Saved geometry for activity {activity.id} with {len(swapped_coords)} points")


def calc_ridden_segments(activity: Activity):
    start_time = time.time()
    logger.info(f"Calculating segments for activity: {activity.strava_id}")

    if not activity.geom:
        calc_line_geom(activity)

    buffer_width = 50 / 40000000 * 360 # roughly 50 meters
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

    logger.info(f"Found {segments.count()} segments for activity: {activity.strava_id}")
    logger.info(f"Calculated segments for activity: {activity.strava_id} in {time.time() - start_time:.4f} seconds")
    

def sync_strava_activity(user, activity_id, update=False):
    start_time = time.time()
    logger.info(f"Starting to parse Strava activity: {activity_id} for user: {user.username}, update: {update}")
    
    exists = Activity.objects.filter(strava_id=activity_id).exists()
    logger.debug(f"Activity {activity_id} exists: {exists}")

    if not update and exists:
        logger.info(f"Strava activity {activity_id} already exists in the database.")
        return
    
    activity = load_activity(user, activity_id)
    if not activity:
        logger.error(f"Strava activity {activity_id} not found")
        raise ValueError(f"Strava activity {activity_id} not found")
    
    if not activity.type == 'AlpineSki':
        logger.warning(f"Strava activity {activity_id} is not an AlpineSki activity.")
        raise ValueError(f"Strava activity {activity_id} is not an AlpineSki activity.")

    activity_streams = load_activity_streams(user, activity_id)

    lat, lon = activity_streams["latlng"].data[0]
    start_point = Point(lon, lat)
    activity_laps = load_activity_laps(user, activity_id)
    start_lift = get_closest_aerialway(start_point, in_ski_area=True, max_distance=2000)
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

    ski_area = get_ski_area(start_point)

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
        "start_time": activity.start_date_local, # TODO: add timezone
        "timestamp": activity.start_date_local, # TODO: add timezone
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
    logger.info(f'{"Created" if created else "Updated"} Activity: {activity_instance.id}')

    if not created:
        activity_instance.laps.all().delete()
        logger.info(f"Deleted existing laps for Activity: {activity_instance.id}")

    cumulative_elapsed_time = timedelta(seconds=0)
    activity_start = activity_instance.start_time

    for lap in activity_laps:
        start_time = activity_start + cumulative_elapsed_time
        cumulative_elapsed_time += timedelta(seconds=lap.elapsed_time)
        end_time = start_time + cumulative_elapsed_time    
        lap_data = {
            "start_time": start_time,
            "timestamp": start_time,
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
            "end_time": end_time,
        }
        lap_instance, created = Lap.objects.update_or_create(lap_index=lap.lap_index, activity=activity_instance, defaults=lap_data)
        logger.info(f'{"Created" if created else "Updated"} Lap: {lap_instance.lap_index}')

    logger.debug(f"Number of laps: {activity_instance.laps.count()}")
    if activity_instance.laps.count() == 1 or \
        (activity_instance.laps.count() > 30 and \
        activity_instance.timestamp < datetime(year=2019, month=12, day=31)):
    # no auto pause used or old activities with bad lap data
        activity_instance.laps.all().delete()
        split_activity(activity_instance, activity_streams)

    for lap in activity_instance.laps.all():
        logger.debug(f"Processing Lap: {lap.lap_index}")
        logger.debug(f"Start Position (Lap): {get_osm_url(lap.start_position)} at {lap.start_time}")
        logger.debug(f"End Position (Lap): {get_osm_url(lap.end_position)} at {lap.end_time}")
        lift_end_pos = lap.start_position
        prev_lap = Lap.objects.filter(activity=activity_instance, lap_index=lap.lap_index-1).first()
        if prev_lap:
            lift_start_pos = prev_lap.end_position
            lift_start_time = prev_lap.end_time
        else:
            lift_start_pos = None
            lift_start_time = lap.start_time
        #lift_start_pos = Lap.objects.filter(activity=activity_instance, lap_index=lap.lap_index-1).first().end_position if lap.lap_index > 1 else None
        lift_rides = get_aerialways(lift_start_pos, lift_end_pos)
        for (lift_ride, uphill) in lift_rides:
            logger.debug(lift_rides)

            logger.debug(f"Found lift ride: {lift_ride if lift_ride else 'unnamed'}")
            logger.debug(f"Uphill: {uphill}")
            logger.debug(f"lap: {lap}, lift_ride: {lift_ride}, uphill: {uphill}, timestamp: {lift_start_time}")
            lift_ride = apply_exceptions(lift_ride)
            lift, _ = LiftRide.objects.update_or_create(lap=lap, aerialway=lift_ride, uphill=uphill if True else False, timestamp=lift_start_time)
            lift_start_time = lift_start_time + timedelta(minutes=lift.aerialway.aerialway_duration if lift.aerialway.aerialway_duration else 1)
            logger.info(f"Created LiftRide for Lap: {lap.lap_index} with lift {lift_ride.name if lift_ride else 'unnamed'}")
   
    calc_vertical_activity(activity_instance, activity_streams["altitude"].data, update=True)

    calc_line_geom(activity_instance, activity_streams["latlng"].data)

    calc_ridden_segments(activity_instance)

    assign_cost(activity_instance)

    activity_instance.num_laps = activity_instance.laps.count()
    activity_instance.num_lift_rides = activity_instance.laps.aggregate(total_lift_rides=Count('lift_rides'))['total_lift_rides']
    activity_instance.save()

    assign_badges(activity_instance)
    logger.info(f"Assigned badges to activity {activity_instance.id}")

    logger.info(f"Finished parsing Strava activity: {activity_id} in {time.time() - start_time:.4f} seconds")

    return activity_instance

    



