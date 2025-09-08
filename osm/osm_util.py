from .models import Aerialway

def get_aerialways_with_distance(lat, lon, distance_km, srid=4326):
    """
    Returns Aerialways within distance along with their actual distance from the point.
    
    Args:
        latitude (float): Latitude of the center point
        longitude (float): Longitude of the center point
        distance_km (float): Maximum distance in kilometers
        srid (int): Spatial Reference System Identifier (default: 4326 for WGS84)
    
    Returns:
        QuerySet: Aerialway objects annotated with distance field
    """

    deg_radius = distance_km / 111.32  # Rough conversion from km to degrees

    query = """
        SELECT
            st_distance(
                way_start_node.geom,
                ST_SetSRID(ST_MakePoint(%s, %s), %s)
            ) AS distance_from_way_start,
            osm_aerialway.*
        FROM osm_aerialway
        INNER JOIN osm_way
            ON osm_aerialway.way_id = osm_way.id
        INNER JOIN osm_waynode
            ON osm_way.id = osm_waynode.way_id
            AND osm_waynode.sequence = 0
        INNER JOIN osm_node AS way_start_node
            ON osm_waynode.node_id = way_start_node.id
        WHERE ST_DWithin(
                way_start_node.geom,
                ST_SetSRID(ST_MakePoint(%s, %s), %s),
                %s
            )
        AND osm_aerialway.name NOT LIKE 'Unnamed%%'
        ORDER BY distance_from_way_start ASC
    """

    qs = Aerialway.objects.raw(query, [lon, lat, srid, lon, lat, srid, deg_radius])

    return qs