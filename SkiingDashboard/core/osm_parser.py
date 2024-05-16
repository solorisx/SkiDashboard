import osmium
import logging
import time
from SkiingDashboardApp.osm_models import Way, Node, Aerialway, Piste, SkiArea  # Adjust the import path as needed

# Get an instance of a logger
logger = logging.getLogger('SkiingDashboard')

class OSMHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []
        self.nodes = []
        self.relations = []

    def way(self, w):
        way_data = {
            'osm_id': w.id,
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

def process_nodes(handler):
    chunk_size = 1000
    logger.info(f"Starting to process nodes with chunk size {chunk_size}")
    node_chunks = [handler.nodes[i:i + chunk_size] for i in range(0, len(handler.nodes), chunk_size)]
    for i, chunk in enumerate(node_chunks):
        node_objs = [Node(osm_id=node['osm_id'], geom=node['geom'], tags=node.get('tags', {})) for node in chunk]
        Node.objects.bulk_create(node_objs, batch_size=chunk_size, update_conflicts=True, update_fields=['geom', 'tags'], unique_fields=['osm_id'])
        logger.debug(f"Processed {min((i + 1) * chunk_size, len(handler.nodes))} / {len(handler.nodes)} nodes")
        if i % 100 == 0:
            logger.info(f"Processed {round(i * chunk_size / len(handler.nodes) * 100,2)}% ({i * chunk_size} / {len(handler.nodes)} nodes)")
    logger.info("Finished processing nodes")

def process_ways(handler):
    logger.info("Starting to process ways")
    counter = 0
    for way_data in handler.ways:

        way, created = Way.objects.update_or_create(
            osm_id=way_data['osm_id'],
            defaults={'tags': way_data.get('tags', {})}
        )
        logger.debug(f"{'Created' if created else 'Updated'} way: {way_data['osm_id']}")

        # Associate nodes with this way
        for node_id in way_data['nodes']:
            try:
                node = Node.objects.get(osm_id=node_id)
                way.nodes.add(node)
            except Node.DoesNotExist:
                logger.warning(f"Node {node_id} does not exist for way {way_data['osm_id']}")

        # Handle Aerialway
        if 'aerialway' in way.tags:
            Aerialway.objects.update_or_create(
                way=way,
                defaults={
                    'aerialway': way.tags['aerialway'],
                    'aerialway_bubble': 'bubble' in way.tags and way.tags['bubble'] == 'yes',
                    'aerialway_capacity': way.tags.get('capacity'),
                    'aerialway_duration': way.tags.get('duration'),
                    'aerialway_heating': 'heating' in way.tags and way.tags['heating'] == 'yes',
                    'aerialway_occupancy': way.tags.get('occupancy'),
                    'name': way.tags.get('name'),
                    'station_nodes': way.nodes.filter(tags__contains={'aerialway': 'station'})
                }
            )
            logger.debug(f"Processed aerialway for way: {way_data['osm_id']}")

        # Handle Piste
        elif 'piste:type' in way.tags:
            Piste.objects.update_or_create(
                way=way,
                defaults={
                    'lit': 'lit' in way.tags and way.tags['lit'] == 'yes',
                    'name': way.tags.get('name'),
                    'oneway': 'oneway' in way.tags and way.tags['oneway'] == 'yes',
                    'piste_difficulty': way.tags.get('piste:difficulty'),
                    'piste_grooming': way.tags.get('piste:grooming'),
                    'piste_type': way.tags['piste:type'],
                    'ref': way.tags.get('ref')
                }
            )
            logger.debug(f"Processed piste for way: {way_data['osm_id']}")
        else:
            counter += 1
            logger.debug(f"No aerialway or piste, way: {way_data['osm_id']}, count {counter}")
    logger.info("Finished processing ways")
    
def process_relations(handler):
        logger.info("Starting to process relations")
        for relation_data in handler.relations:
            ski_area, created = SkiArea.objects.update_or_create(
                osm_id=relation_data['osm_id'],
                defaults={
                    'name': relation_data['name'],
                    'url': relation_data['url'],
                    'wikipedia': relation_data['wikipedia']
                }
            )
            logger.debug(f"{'Created' if created else 'Updated'} ski area: {relation_data['osm_id']}")

            # Associate ways with this ski area
            for way_id in relation_data['member_ids']:
                try:
                    way = Way.objects.get(osm_id=way_id)
                    ski_area.ways.add(way)
                except Way.DoesNotExist:
                    logger.warning(f"Way {way_id} does not exist for ski area {relation_data['osm_id']}")
                    pass
        logger.info("Finished processing relations")

def parse_osm_file(file_path):
    logger.info(f"Starting to parse OSM file: {file_path}")
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
    logger.info(f"Number of relations: {len(handler.relations)}")

    # Process and save or update nodes
    process_nodes(handler)

    # Process and save or update ways, aerialways, and pistes
    process_ways(handler)

    # Process and save or update ski areas
    process_relations(handler)

    total_duration = time.time() - start_time
    logger.info(f"Finished parsing OSM file: {file_path} in {total_duration:.4f} seconds")
