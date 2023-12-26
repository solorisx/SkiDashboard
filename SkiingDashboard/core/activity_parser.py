from fitparse import FitFile
from SkiingDashboardApp.activity_models import Activity, Lap, Record, LiftRide
from SkiingDashboardApp.osm_models import Node, Way, Aerialway
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance


def extract_data(message, model_fields):
    """
    Extract data from a FIT message based on the fields available in the corresponding Django model.
    """
    return {
        field: message.get_value(field)
        for field in model_fields
        if message.get_value(field) is not None
    }


def create_point(lat_field, lon_field, data):
    if lat_field in data and lon_field in data:
        lon = data[lon_field] / 11930465
        lat = data[lat_field] / 11930465
        return Point(lon, lat)
    return None


def get_closest_aerialway(point: Point):
    point.srid = 4326
    closest_station = (
        Node.objects.filter(tags__contains={"aerialway": "station"})
        .annotate(distance=Distance("geom", point))
        .order_by("distance")
        .first()
    )
    if closest_station:
        return Aerialway.objects.filter(station_nodes=closest_station).first()


def parse_fit_file(file_path):
    fitfile = FitFile(file_path)

    activity_data = None
    laps = []
    activity_fields = [f.name for f in Activity._meta.get_fields() if f.name != "laps"]
    lap_fields = [f.name for f in Lap._meta.get_fields() if f.name != "activity"]
    record_fields = [f.name for f in Record._meta.get_fields() if f.name != "lap"]

    # Process each message in the FIT file
    for message in fitfile.get_messages():
        if message.name == "record":
            record_data = extract_data(message, record_fields)
            record_data["position"] = create_point(
                "position_lat", "position_long", record_data
            )
            current_lap_records.append(record_data)

        elif message.name == "lap":
            current_lap_data = extract_data(message, lap_fields)
            current_lap_data["start_position"] = create_point(
                "start_position_lat", "start_position_long", current_lap_data
            )
            current_lap_data["end_position"] = create_point(
                "end_position_lat", "end_position_long", current_lap_data
            )
            current_lap_data["records"] = current_lap_records
            laps.append(current_lap_data)
            current_lap_records = []

        elif message.name == "session":
            activity_data = extract_data(message, activity_fields)

    if not activity_data:
        raise ValueError("No session found in FIT file.")

    # Create Activity instance
    activity = Activity.objects.create(**activity_data)

    # Create Lap and Record instances
    for lap_data in laps:
        # Remove the separate latitude and longitude fields
        lap_data.pop("start_position_lat", None)
        lap_data.pop("start_position_long", None)
        lap_data.pop("end_position_lat", None)
        lap_data.pop("end_position_long", None)

        lap = Lap.objects.create(activity=activity, **lap_data)

        lift_ride = get_closest_aerialway(lap.start_position)

        if lift_ride:
            LiftRide.objects.create(
                lap=lap, aerialway=lift_ride, timestamp=lap.start_time
            )

        for record_data in lap_data["records"]:
            # Remove the separate latitude and longitude fields
            record_data.pop("position_lat", None)
            record_data.pop("position_long", None)

            Record.objects.create(lap=lap, **record_data)
