import overpy
import logging

logger = logging.getLogger('core')

def get_osm_data(osm_id, osm_type):
    api = overpy.Overpass()
    if osm_type == "Node":
        result = api.query(f"node({osm_id});out;")
    elif osm_type == "Way":
        result = api.query(f"way({osm_id});out;")
    elif osm_type == "Relation":
        result = api.query(f"relation({osm_id});out;")
    else:
        raise ValueError(f"Invalid OSM type: {osm_type}")
    return result

def load_osm_data(osm_id, osm_type):
    result = get_osm_data(osm_id, osm_type)
    logger.debug(len(result.nodes))
    logger.debug(len(result.ways))
    nodes = result.ways[0].get_nodes(resolve_missing=True)
    logger.debug(len(nodes))
    for node in nodes:
        logger.debug(node)

