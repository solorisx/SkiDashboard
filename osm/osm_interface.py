import overpy

def get_osm_data(osm_id, osm_type):
    api = overpy.Overpass()
    if osm_type == "node":
        result = api.query(f"node({osm_id});out;")
    elif osm_type == "way":
        result = api.query(f"way({osm_id});out;")
    elif osm_type == "relation":
        result = api.query(f"relation({osm_id});out;")
    else:
        raise ValueError(f"Invalid OSM type: {osm_type}")
    return result

def load_osm_data(osm_id, osm_type):
    result = get_osm_data(osm_id, osm_type)
    data = []
    # TODO: save data to database