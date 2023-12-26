import osmium
from SkiingDashboardApp.osm_models import Way, Node, Aerialway, Piste, SkiArea  # Adjust the import path as needed

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

def parse_osm_file(file_path):
    handler = OSMHandler()
    handler.apply_file(file_path, locations=True)

    # Process and save or update nodes
    for node_data in handler.nodes:
        Node.objects.update_or_create(
            osm_id=node_data['osm_id'],
            defaults={'geom': node_data['geom'], 'tags': node_data.get('tags', {})}
        )

    # Process and save or update ways, aerialways, and pistes
    for way_data in handler.ways:
        way, created = Way.objects.update_or_create(
            osm_id=way_data['osm_id'],
            defaults={'tags': way_data.get('tags', {})}
        )

        # Associate nodes with this way
        for node_id in way_data['nodes']:
            node = Node.objects.get(osm_id=node_id)
            way.nodes.add(node)

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

    # Process and save or update ski areas
    for relation_data in handler.relations:
        ski_area, created = SkiArea.objects.update_or_create(
            osm_id=relation_data['osm_id'],
            defaults={
                'name': relation_data['name'],
                'url': relation_data['url'],
                'wikipedia': relation_data['wikipedia']
            }
        )
        # Associate ways with this ski area
        for way_id in relation_data['member_ids']:
            try:
                way = Way.objects.get(osm_id=way_id)
                ski_area.ways.add(way)
            except Way.DoesNotExist:
                # TODO: add some logging or add call to OSM API
                pass