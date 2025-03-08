import osmium
import osmium.geom
import logging
import time
from .models import Way, Node, Aerialway, Piste, SkiArea, Station, SkiAreaBoundary
from django.db import transaction
from django.db.models import Q

# Get an instance of a logger
logger = logging.getLogger(__name__)
wkbfab = osmium.geom.WKBFactory()

class OSMHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []
        self.nodes = []
        self.areas = []
        self.relations = []

    def way(self, w):
        way_data = {
            'osm_id': w.id,
            'geom': wkbfab.create_linestring(w),
            'nodes': [n.ref for n in w.nodes],
            'tags': dict(w.tags)
        }
        self.ways.append(way_data)

    def node(self, n):
        node_data = {
            'osm_id': n.id,
            'geom': f'POINT({n.location.lon} {n.location.lat})',
            'tags': dict(n.tags)
        }
        self.nodes.append(node_data)

    def area(self, a):
        if 'landuse' in a.tags and a.tags['landuse'] == 'winter_sports':
            area_data = {
                'osm_id': a.orig_id(),
                'geom': wkbfab.create_multipolygon(a),
                'name': a.tags.get('name'),
                'tags': dict(a.tags)
            }
            self.areas.append(area_data)

    def relation(self, r):
        if 'site' in r.tags and r.tags['site'] == 'piste':
            relation_data = {
                'osm_id': r.id,
                'name': r.tags.get('name'),
                'url': r.tags.get('url'),
                'wikipedia': r.tags.get('wikipedia'),
                'member_ids': [member.ref for member in r.members if member.type == 'w']
            }
            self.relations.append(relation_data)

def duration_to_minutes(duration):
    try:
        minutes = duration.split(':')
        return int(minutes[0])
    except:
        return None
    
def ele_to_float(ele):
    try:
        # format 1234.56m
        ele = ele.replace('m', '')
        return float(ele)
    except:
        return None
    
def str_to_int(s):
    try:
        return int(s)
    except:
        return None

def process_nodes(handler):
    chunk_size = 1000
    logger.info(f"Starting to process nodes with chunk size {chunk_size}")
    node_chunks = [handler.nodes[i:i + chunk_size] for i in range(0, len(handler.nodes), chunk_size)]
    for i, chunk in enumerate(node_chunks):
        try:
            node_objs = [Node(osm_id=node['osm_id'], geom=node['geom'], tags=node.get('tags', {})) for node in chunk]
            Node.objects.bulk_create(node_objs, batch_size=chunk_size, update_conflicts=True, update_fields=['geom', 'tags'], unique_fields=['osm_id'])
            logger.debug(f"Processed {min((i + 1) * chunk_size, len(handler.nodes))} / {len(handler.nodes)} nodes")
            if i % 100 == 0:
                logger.info(f"Processed {round(i * chunk_size / len(handler.nodes) * 100,2)}% ({i * chunk_size} / {len(handler.nodes)} nodes)")
        except Exception as e:
            logger.error(f"Error processing chunk {i} of nodes: {e}")
    logger.info("Finished processing nodes")

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def fetch_nodes_in_batches(node_ids, batch_size=1000):
    nodes_dict = {}
    for chunk in chunks(list(node_ids), batch_size):
        nodes = Node.objects.filter(osm_id__in=chunk)
        nodes_dict.update({node.osm_id: node for node in nodes})
    return nodes_dict

def process_ways(handler):

    chunk_size = 1000
    logger.info(f"Starting to process way with chunk size {chunk_size}")

    # Split handler.ways into chunks
    ways_chunks = [handler.ways[i:i + chunk_size] for i in range(0, len(handler.ways), chunk_size)]

    for i, chunk in enumerate(ways_chunks):
        try:
            # Create Way objects without assigning nodes
            way_objs = [Way(osm_id=way['osm_id'], tags=way.get('tags', {})) for way in chunk]
            Way.objects.bulk_create(way_objs, batch_size=chunk_size, update_conflicts=True, update_fields=['tags'], unique_fields=['osm_id'])

            logger.info(f"Created {len(way_objs)} ways")

            # Fetch the created ways to update nodes
            osm_ids = [way['osm_id'] for way in chunk]
            ways = Way.objects.filter(osm_id__in=osm_ids)
            ways_dict = {way.osm_id: way for way in ways}

            # Fetch all nodes required in this chunk
            node_ids = {node_id for way in chunk for node_id in way['nodes']}
            nodes = Node.objects.filter(osm_id__in=node_ids)
            nodes_dict = {node.osm_id: node for node in nodes}

            way_nodes_to_create = []
            way_nodes_to_update = []

            with transaction.atomic():
                for way_data in chunk:
                    way = ways_dict[way_data['osm_id']]
                    node_instances = [nodes_dict[node_id] for node_id in way_data['nodes'] if node_id in nodes_dict]

                    existing_way_nodes = {
                        wn.node.osm_id: wn for wn in way.nodes.through.objects.filter(way=way)
                    }

                    logger.debug(f"Processing way {way.osm_id} with {len(node_instances)} nodes")
                    logger.debug(existing_way_nodes)

                    new_node_ids = set(way_data['nodes'])
                    existing_node_ids = set([way_node.node.osm_id for way_node in existing_way_nodes.values()]
)

                    logger.debug(f"new_node_ids: {new_node_ids}")
                    logger.debug(f"existing_node_ids {existing_node_ids}")

                    # Identify WayNodes to delete (those that are no longer in way_data['nodes'])
                    nodes_to_delete = existing_node_ids - new_node_ids

                    logger.debug(f"nodes_to_delete: {nodes_to_delete}")

                    way.nodes.through.objects.filter(way=way, node_id__in=nodes_to_delete).delete()
                    if nodes_to_delete:
                        logger.info(f"Deleted {len(nodes_to_delete)} WayNodes for way {way.osm_id}")
                    else:
                        logger.debug(f"No WayNodes to delete for way {way.osm_id}")

                    # Process each node in the way
                    for sequence, node_id in enumerate(way_data['nodes']):
                        if node_id in nodes_dict:  # Ensure node exists
                            if node_id in existing_node_ids:
                                # Update existing WayNode sequence
                                existing_way_nodes[node_id].sequence = sequence
                                way_nodes_to_update.append(existing_way_nodes[node_id])
                            else:
                                # Create new WayNode instance
                                way_nodes_to_create.append(
                                    way.nodes.through(way=way, node=nodes_dict[node_id], sequence=sequence)
                                )

                logger.info(f"{len(way_nodes_to_create)} WayNodes to create")
                logger.info(f"{len(way_nodes_to_update)} WayNodes to update")
                
                # Bulk create new WayNode instances
                if way_nodes_to_create:
                    way.nodes.through.objects.bulk_create(way_nodes_to_create, batch_size=chunk_size)

                # Bulk update existing WayNode instances
                if way_nodes_to_update:
                    way.nodes.through.objects.bulk_update(way_nodes_to_update, ["sequence"], batch_size=chunk_size)

                if way_nodes_to_create or nodes_to_delete:
                    logger.warning(f"Processed added/deleted WayNodes for way {way.osm_id}")

            logger.info(f"Processed {min((i + 1) * chunk_size, len(handler.ways))} / {len(handler.ways)} ways")
            if i % 100 == 0:
                logger.info(f"Processed {round(i * chunk_size / len(handler.ways) * 100, 2)}% ({i * chunk_size} / {len(handler.ways)} ways)")
        except Exception as e:
            logger.error(f"Error processing chunk {i} of ways: {e}")
            raise e
    logger.info("Finished processing ways")

    logger.info("Starting to process aerialways and pistes")
    counter = 0

    for way in handler.ways:
        try:
            tags=way.get('tags', {})
            nodes=way.get('nodes', [])

            way_obj = Way.objects.get(osm_id=way['osm_id'])
            if way_obj is None:
                logger.warning(f"Way {way['osm_id']} does not exist")
                continue

            with transaction.atomic():    

                # Handle Aerialway
                if 'aerialway' in tags:
                    # Get nodes associated with this way
                    nodes = way.get('nodes', [])
                    node_instances = Node.objects.filter(osm_id__in=nodes)
                    aerialway, created = Aerialway.objects.update_or_create(
                        way=way_obj,
                        defaults={
                            'aerialway': tags.get('aerialway'),
                            'aerialway_bubble': 'bubble' in tags and tags['bubble'] == 'yes',
                            'aerialway_capacity': str_to_int(tags.get('aerialway:capacity')),
                            'aerialway_duration': duration_to_minutes(tags.get('aerialway:duration')),
                            'aerialway_heating': 'heating' in tags and tags['aerialway:heating'] == 'yes',
                            'aerialway_occupancy': str_to_int(tags.get('aerialway:occupancy')),
                            'name': tags.get('name')[0:255] if 'name' in tags else f"Unnamed aerialway {way['osm_id']}",
                        }
                    )
                    station_nodes = [node for node in node_instances if node.tags.get('aerialway') == 'station']
                    stations = []
                    for node in station_nodes:
                        station, created = Station.objects.update_or_create(
                            node=node,
                            defaults={
                                'name': node.tags.get('name'),
                                'altitude': ele_to_float(node.tags.get('ele')),
                                'station': node.tags.get('aerialway:station')
                            }
                        )
                        stations.append(station)
                        
                    aerialway.station_nodes.set(stations)
                    aerialway.bottom_station = aerialway.station_nodes.filter(station='bottom').first()
                    aerialway.top_station = aerialway.station_nodes.filter(station='top').first()
                    aerialway.save()
                    logger.debug(f"Processed aerialway for way: {way['osm_id']}")

                # Handle Piste
                elif 'piste:type' in tags:
                    if way_obj.nodes.first() == way_obj.nodes.last():
                        # TODO: add support for polygons
                        logger.warning(f"Piste {way['osm_id']} has the same start and end node, probably a polygon - not supported")
                        continue
                    Piste.objects.update_or_create(
                        way=way_obj,
                        defaults={
                            'lit': 'lit' in tags and tags['lit'] == 'yes',
                            'name': tags.get('name')[0:255] if 'name' in tags else None,
                            'oneway': 'oneway' in tags and tags['oneway'] == 'yes',
                            'piste_difficulty': tags.get('piste:difficulty'),
                            'piste_grooming': tags.get('piste:grooming'),
                            'piste_type': tags.get('piste:type'),
                            'ref': tags.get('ref')
                        }
                    )
                    logger.debug(f"Processed piste for way: {way['osm_id']}")
                else:
                    counter += 1
                    logger.debug(f"No aerialway or piste, way: {way['osm_id']}, count {counter}")
        except Exception as e:
            logger.error(f"Error processing way {way['osm_id']} with tags {tags}: {e}")

    logger.info("Finished processing ways")
    
def process_areas(handler):
    logger.info("Starting to process areas")
    for area_data in handler.areas:
        try:
            with transaction.atomic():
                name = area_data['name'] or f"Unnamed area {area_data['osm_id']}"
                way = Way.objects.filter(osm_id=area_data['osm_id']).first()
                if way is None:
                    logger.info(f"Way {area_data['osm_id']} for area {name} does not exist")
                    way = Way.objects.create(osm_id=area_data['osm_id'], tags=area_data.get('tags', {}))
                    logger.info(f"Created way {area_data['osm_id']} for area {name} with tags {area_data.get('tags', {})}")

                _, created = SkiAreaBoundary.objects.update_or_create(
                    way=way,
                    defaults={
                        'geom': area_data['geom'],
                        'name': area_data['name'] or f"Unnamed area {area_data['osm_id']}"
                    }
                )
                logger.debug(f"{'Created' if created else 'Updated'} ski area boundary: {area_data['osm_id']}")


                _, created = SkiArea.objects.update_or_create(
                    osm_id=way.osm_id,
                    way=way,
                    defaults={
                        'geom': area_data['geom'],
                        'name': area_data['name'] or f"Unnamed area {area_data['osm_id']}",
                        'tags': area_data.get('tags', {})
                    }
                )
                logger.debug(f"{'Created' if created else 'Updated'} ski area: {area_data['osm_id']}")




                    # Associate aerialway and pistes with this ski area boundary
                    # TODO

        except Exception as e:
            logger.error(f"Error processing area {area_data['osm_id']}: {e}")

    logger.info("Finished processing areas")


def process_relations(handler):
        logger.info("Starting to process relations")
        for relation_data in handler.relations:
            try:
                with transaction.atomic():
                    ski_area, created = SkiArea.objects.update_or_create(
                        osm_id=relation_data['osm_id'],
                        defaults={
                            'name': relation_data['name'] or f"Unnamed relation {relation_data['osm_id']}",
                            'url': relation_data['url'],
                            'wikipedia': relation_data['wikipedia'],
                            'tags': relation_data.get('tags', {})
                        }
                    )
                    if relation_data['name'] is None:
                        logger.warning(f"Relation {relation_data['osm_id']} has no name")
                    logger.debug(f"{'Created' if created else 'Updated'} ski area: {relation_data['osm_id']}")

                    # Associate ways with this ski area
                    for way_id in relation_data['member_ids']:
                        way = Way.objects.filter(osm_id=way_id).first()
                        if way:
                            ski_area.ways.add(way)
                        else:
                            logger.warning(f"Way {way_id} does not exist for ski area {relation_data['osm_id']}")
            except Exception as e:
                logger.error(f"Error processing relation {relation_data['osm_id']}, {relation_data}: {e}")
        logger.info("Finished processing relations")


def parse_osm_file(file_path, scope):
    logger.info(f"Starting to parse OSM file: {file_path}")
    logger.info(f"{'parsing' if scope[0] else 'skipping'} nodes, {'parsing' if scope[1] else 'skipping'} ways, {'parsing' if scope[2] else 'skipping'} relations")
    start_time = time.time()

    logger.info(f"Starting to apply OSM file to handler: {file_path}")
    start_time_handler = time.time()
    handler = OSMHandler()
    handler.apply_file(file_path, locations=True)
    total_duration_handler = time.time() - start_time_handler
    logger.info(f"Applied OSM file to handler in {total_duration_handler:.4f} seconds")

    # Get the number of nodes, ways, and relations
    logger.info(f"Number of nodes: {len(handler.nodes)}")
    logger.info(f"Number of ways: {len(handler.ways)}")
    logger.info(f"Number of areas: {len(handler.areas)}")
    logger.info(f"Number of relations: {len(handler.relations)}")

    # Process and save or update nodes
    if scope[0]:
        process_nodes(handler)

    # Process and save or update ways, aerialways, and pistes
    if scope[1]:
        process_ways(handler)

    # Process and save or update ski areas
    if scope[2]:
        process_relations(handler)

    if scope[3]:
        process_areas(handler)

    total_duration = time.time() - start_time
    logger.info(f"Finished parsing OSM file: {file_path} in {total_duration:.4f} seconds")

