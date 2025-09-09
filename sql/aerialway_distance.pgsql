SELECT 
    st_distance(way_start_node.geom, ST_SetSRID(ST_MakePoint(9.848187,46.772275),4326)) AS distance_from_way_start,
    osm_aerialway.*
FROM osm_aerialway
INNER JOIN osm_way on osm_aerialway.way_id = osm_way.id
INNER JOIN osm_waynode on osm_way.id = osm_waynode.way_id and osm_waynode.sequence = 0
INNER JOIN osm_node as way_start_node on osm_waynode.node_id = way_start_node.id
WHERE ST_DWithin("way_start_node"."geom", ST_SetSRID(ST_MakePoint(9.848187,46.772275),4326), 100/111.32)
AND osm_aerialway.name not like 'Unnamed%'
ORDER BY distance_from_way_start ASC
;