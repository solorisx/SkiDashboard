from fitparse import FitFile
from SkiingDashboardApp.activity_models import Activity, Lap, Record  # Adjust import path as needed
from django.contrib.gis.geos import Point

def extract_data(message, model_fields):
    """
    Extract data from a FIT message based on the fields available in the corresponding Django model.
    """
    return {field: message.get_value(field) for field in model_fields if message.get_value(field) is not None}

def parse_fit_file(file_path):
    fitfile = FitFile(file_path)

    activity_data = None
    laps = []
    activity_fields = [f.name for f in Activity._meta.get_fields() if f.name != 'laps']
    lap_fields = [f.name for f in Lap._meta.get_fields() if f.name != 'activity']
    record_fields = [f.name for f in Record._meta.get_fields() if f.name != 'lap']

def create_point(lat_field, lon_field, data):
    if lat_field in data and lon_field in data:
        return Point(data[lon_field], data[lat_field])
    return None

    # Process each message in the FIT file
    for message in fitfile.get_messages():

        if message.name == 'record':
            record_data = extract_data(message, record_fields)
            record_data['position'] = create_point('position_lat', 'position_long', record_data)
            current_lap_records.append(record_data)

        elif message.name == 'lap':
            current_lap_data = extract_data(message, lap_fields)
            current_lap_data['start_position'] = create_point('start_position_lat', 'start_position_long', current_lap_data)
            current_lap_data['end_position'] = create_point('end_position_lat', 'end_position_long', current_lap_data)
            current_lap_data['records'] = current_lap_records
            laps.append(current_lap_data)
            current_lap_records = []
    
        elif message.name == 'session':
            activity_data = extract_data(message, activity_fields)

    if not activity_data:
        raise ValueError("No session found in FIT file.")

    # Create Activity instance
    activity = Activity.objects.create(**activity_data)

    # Create Lap and Record instances
    for lap_data in laps:
        # Remove the separate latitude and longitude fields
        lap_data.pop('start_position_lat', None)
        lap_data.pop('start_position_long', None)
        lap_data.pop('end_position_lat', None)
        lap_data.pop('end_position_long', None)

        lap = Lap.objects.create(activity=activity, **lap_data)

        for record_data in lap_data['records']:
            # Remove the separate latitude and longitude fields
            record_data.pop('position_lat', None)
            record_data.pop('position_long', None)
            
            Record.objects.create(lap=lap, **record_data)

