import overpy
import logging
import requests

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

def get_country_code(osm_id, osm_type):
    try:
        result = get_osm_data(osm_id, osm_type)
        
        node = None

        if osm_type == "Way":
            way = result.ways[0]
            nodes = way.get_nodes(resolve_missing=True)
            node = nodes[0] if nodes else None

        elif osm_type == "Relation":
            relation = result.relations[0]
            relation_nodes = [
                member for member in relation.members
                if isinstance(member, overpy.RelationNode)
            ]
            if not relation_nodes:
                logger.debug(f"No nodes found in relation {osm_id}")
                return None
            node = relation_nodes[0].resolve(resolve_missing=True)

        else:
            raise ValueError(f"Invalid OSM type: {osm_type}")

        if not node:
            logger.debug(f"No node found for OSM ID {osm_id}")
            return None

        # Try to get country code from node tags
        if node.tags:
            logger.debug(f"Node tags for {osm_id}: {node.tags}")
            country_code = node.tags.get("addr:country")
            if country_code:
                logger.debug(f"Country code for node {osm_id}: {country_code}")
                return country_code

        # Fallback to reverse geocoding using Nominatim
        logger.debug(f"Fetching country code from Nominatim API for node {osm_id}")
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={node.lat}&lon={node.lon}"
        response = requests.get(url, headers={"User-Agent": "SkiDashboard/1.0"})

        if response.ok:
            data = response.json()
            country_code = data.get("address", {}).get("country_code")
            if country_code:
                logger.debug(f"Country code from Nominatim API for node {osm_id}: {country_code}")
                return country_code
            else:
                logger.debug(f"No country code found in Nominatim API response for node {osm_id}")
        else:
            logger.error(f"Nominatim API request failed with status code: {response.status_code}")

    except Exception as e:
        logger.exception(f"An error occurred while fetching country code for OSM ID {osm_id}: {e}")

    return None


if __name__ == "__main__":
    # Example usage
    osm_id = "3508010"
    osm_type = "Relation"
    country_code = get_country_code(osm_id, osm_type)
    if country_code:
        print(f"Country code: {country_code}")
    else:
        print("Country code not found.")

    # Example usage
    osm_id = "1252016128"
    osm_type = "Way"
    country_code = get_country_code(osm_id, osm_type)
    if country_code:
        print(f"Country code: {country_code}")
    else:
        print("Country code not found.")

