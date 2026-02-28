import osmium
import osmium.geom
import logging
import time
from datetime import datetime
from django.utils import timezone
from .models import Way, Node, Aerialway, Piste, SkiArea, Station, SkiAreaBoundary
from django.db import transaction
from django.db.models import Q

# Get an instance of a logger
logger = logging.getLogger(__name__)
wkbfab = osmium.geom.WKBFactory()

class OSMHandler(osmium.SimpleHandler):
    def __init__(self, scope):
        osmium.SimpleHandler.__init__(self)
        self.scope = scope
        self.nodes = [] if scope[0] else None
        self.ways = [] if scope[1] else None  
        self.relations = [] if scope[2] else None
        self.areas = [] if scope[3] else None
        self.processed_count = 0

    def way(self, w):
        if self.ways is not None:
            way_data = {
                'osm_id': w.id,
                'geom': wkbfab.create_linestring(w),
                'nodes': [n.ref for n in w.nodes],
                'tags': dict(w.tags)
            }
            self.ways.append(way_data)

    def node(self, n):
        if self.nodes is not None:
            node_data = {
                'osm_id': n.id,
                'geom': f'POINT({n.location.lon} {n.location.lat})',
                'tags': dict(n.tags)
            }
            self.nodes.append(node_data)

    def area(self, a):
        if self.areas is not None:
            if 'landuse' in a.tags and a.tags['landuse'] == 'winter_sports':
                area_data = {
                    'osm_id': a.orig_id(),
                    'geom': wkbfab.create_multipolygon(a),
                    'name': a.tags.get('name'),
                    'tags': dict(a.tags)
                }
                self.areas.append(area_data)

    def relation(self, r):
        if self.relations is not None:
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
    verification_time = timezone.now()
    for i, chunk in enumerate(node_chunks):
        try:
            node_objs = [Node(osm_id=node['osm_id'], geom=node['geom'], tags=node.get('tags', {}), verified_on=verification_time) for node in chunk]
            Node.objects.bulk_create(node_objs, batch_size=chunk_size, update_conflicts=True, update_fields=['geom', 'tags', 'verified_on'], unique_fields=['osm_id'])
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

def create_stations_from_way_endpoints(aerialway, way_obj, verification_time=None):
    """
    Create station nodes for an aerialway using its first and last way nodes.

    Used when OSM data does not include explicit station nodes (aerialway=station)
    for an aerial way. The first and last nodes of the way are used as the
    bottom and top station locations. Elevation tags are used to determine which
    end is the bottom (lower) and which is the top (higher); when elevation is
    unavailable the first node in sequence is treated as the bottom station.

    Args:
        aerialway: The Aerialway model instance to associate stations with.
        way_obj: The Way model instance.
        verification_time: Optional datetime for the verified_on field.

    Returns:
        list: The two Station objects [bottom_station, top_station], or an empty
              list when the way has fewer than two nodes.
    """
    if verification_time is None:
        verification_time = timezone.now()

    ordered_nodes = way_obj.nodes.order_by('waynode__sequence')
    if ordered_nodes.count() < 2:
        logger.warning(
            f"Way {way_obj.osm_id} has fewer than 2 nodes, cannot create endpoint stations"
        )
        return []

    first_node = ordered_nodes.first()
    last_node = ordered_nodes.last()

    first_ele = ele_to_float(first_node.tags.get('ele'))
    last_ele = ele_to_float(last_node.tags.get('ele'))

    # Determine bottom/top by elevation when available; fall back to way order.
    if first_ele is not None and last_ele is not None:
        if first_ele <= last_ele:
            bottom_node, top_node = first_node, last_node
            bottom_ele, top_ele = first_ele, last_ele
        else:
            bottom_node, top_node = last_node, first_node
            bottom_ele, top_ele = last_ele, first_ele
    else:
        bottom_node, top_node = first_node, last_node
        bottom_ele = first_ele
        top_ele = last_ele

    aerialway_name = aerialway.name or f"Aerialway {way_obj.osm_id}"

    bottom_station, _ = Station.objects.update_or_create(
        node=bottom_node,
        defaults={
            'name': bottom_node.tags.get('name') or f"{aerialway_name} Bottom",
            'altitude': bottom_ele,
            'station': 'bottom',
            'verified_on': verification_time,
        }
    )

    top_station, _ = Station.objects.update_or_create(
        node=top_node,
        defaults={
            'name': top_node.tags.get('name') or f"{aerialway_name} Top",
            'altitude': top_ele,
            'station': 'top',
            'verified_on': verification_time,
        }
    )

    stations = [bottom_station, top_station]
    aerialway.station_nodes.set(stations)
    aerialway.bottom_station = bottom_station
    aerialway.top_station = top_station
    aerialway.save()

    logger.info(
        f"Created endpoint stations for aerialway {way_obj.osm_id}: "
        f"bottom node={bottom_node.osm_id}, top node={top_node.osm_id}"
    )
    return stations


def process_ways(handler):

    chunk_size = 1000
    logger.info(f"Starting to process way with chunk size {chunk_size}")
    verification_time = timezone.now()

    # Split handler.ways into chunks
    ways_chunks = [handler.ways[i:i + chunk_size] for i in range(0, len(handler.ways), chunk_size)]

    for i, chunk in enumerate(ways_chunks):
        try:
            # Create Way objects without assigning nodes
            way_objs = [Way(osm_id=way['osm_id'], tags=way.get('tags', {}), verified_on=verification_time) for way in chunk]
            Way.objects.bulk_create(way_objs, batch_size=chunk_size, update_conflicts=True, update_fields=['tags', 'verified_on'], unique_fields=['osm_id'])

            logger.debug(f"Created {len(way_objs)} ways")

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

            logger.debug(f"Processed {min((i + 1) * chunk_size, len(handler.ways))} / {len(handler.ways)} ways")
            if i % 10000 == 0:
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
                            'verified_on': verification_time,
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
                                'station': node.tags.get('aerialway:station'),
                                'verified_on': verification_time,
                            }
                        )
                        stations.append(station)

                    aerialway.station_nodes.set(stations)
                    aerialway.bottom_station = aerialway.station_nodes.filter(station='bottom').first()
                    aerialway.top_station = aerialway.station_nodes.filter(station='top').first()
                    aerialway.save()

                    # If no station nodes found in OSM data, create stations from way endpoints
                    if not stations:
                        create_stations_from_way_endpoints(aerialway, way_obj, verification_time)
                        logger.info(f"Created endpoint stations for aerialway without station nodes: {way['osm_id']}")

                    logger.debug(f"Processed aerialway for way: {way['osm_id']}")

                # Handle Piste
                elif 'piste:type' in tags:
                    if way_obj.nodes.first() == way_obj.nodes.last():
                        # TODO: add support for polygons
                        logger.warning(f"Piste {way['osm_id']} has the same start and end node, probably a polygon - not supported")
                        continue
                    piste, created = Piste.objects.update_or_create(
                        way=way_obj,
                        defaults={
                            'lit': 'lit' in tags and tags['lit'] == 'yes',
                            'name': tags.get('name')[0:255] if 'name' in tags else tags.get('piste:name') if 'piste:name' in tags else None,
                            'oneway': 'oneway' in tags and tags['oneway'] == 'yes',
                            'piste_difficulty': tags.get('piste:difficulty'),
                            'piste_grooming': tags.get('piste:grooming'),
                            'piste_type': tags.get('piste:type'),
                            'ref': tags.get('ref') if 'ref' in tags else tags.get('piste:ref') if 'piste:ref' in tags else None,
                            'verified_on': verification_time,
                        }
                    )
                    if created or piste.geom is None:
                        piste.update_geometry()
                    logger.debug(f"Processed piste for way: {way['osm_id']}")
                else:
                    counter += 1
                    logger.debug(f"No aerialway or piste, way: {way['osm_id']}, count {counter}")
        except Exception as e:
            logger.error(f"Error processing way {way['osm_id']} with tags {tags}: {e}")

    logger.info("Finished processing ways")
    
def process_areas(handler):
    logger.info("Starting to process areas")
    verification_time = timezone.now()
    for area_data in handler.areas:
        try:
            with transaction.atomic():
                name = area_data['name'] or f"Unnamed area {area_data['osm_id']}"
                way = Way.objects.filter(osm_id=area_data['osm_id']).first()
                if way is None:
                    logger.info(f"Way {area_data['osm_id']} for area {name} does not exist")
                    way = Way.objects.create(osm_id=area_data['osm_id'], tags=area_data.get('tags', {}), verified_on=verification_time)
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
                        'tags': area_data.get('tags', {}),
                        'verified_on': verification_time,
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
        verification_time = timezone.now()
        for relation_data in handler.relations:
            try:
                with transaction.atomic():
                    ski_area, created = SkiArea.objects.update_or_create(
                        osm_id=relation_data['osm_id'],
                        defaults={
                            'name': relation_data['name'] or f"Unnamed relation {relation_data['osm_id']}",
                            'url': relation_data['url'],
                            'wikipedia': relation_data['wikipedia'],
                            'tags': relation_data.get('tags', {}),
                            'verified_on': verification_time,
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

def delete_orphan_nodes(dry_run=False):
    """
    Delete nodes that are not referenced by any ways or stations.
    
    Args:
        dry_run (bool): If True, only count orphan nodes without deleting them.
                       If False, actually delete the orphan nodes.
    
    Returns:
        int: Number of orphan nodes found (and deleted if not dry_run).
    """
    
    # Find nodes that have no associated ways and no associated station
    orphan_nodes = Node.objects.filter(
        ways__isnull=True,  # No ways reference this node
        station__isnull=True  # No station references this node
    )
    
    orphan_count = orphan_nodes.count()
    
    if dry_run:
        logger.info(f"Found {orphan_count} orphan nodes (dry run - not deleting)")
        return orphan_count
    
    if orphan_count == 0:
        logger.info("No orphan nodes found")
        return 0
    
    # Use transaction to ensure atomicity
    with transaction.atomic():
        deleted_count, _ = orphan_nodes.delete()
        logger.info(f"Deleted {deleted_count} orphan nodes")
    
    return deleted_count


def delete_orphan_nodes_batch(batch_size=1000, dry_run=False):
    """
    Delete orphan nodes in batches to avoid memory issues with large datasets.
    
    Args:
        batch_size (int): Number of nodes to process in each batch.
        dry_run (bool): If True, only count orphan nodes without deleting them.
    
    Returns:
        int: Total number of orphan nodes found (and deleted if not dry_run).
    """
    
    total_deleted = 0
    
    while True:
        # Find orphan nodes in batches
        orphan_node_ids = list(
            Node.objects.filter(
                ways__isnull=True,
                station__isnull=True
            ).values_list('id', flat=True)[:batch_size]
        )
        
        if not orphan_node_ids:
            break
        
        if dry_run:
            total_deleted += len(orphan_node_ids)
            logger.info(f"Found batch of {len(orphan_node_ids)} orphan nodes (dry run)")
            # In dry run, we break after first batch to avoid infinite loop
            break
        else:
            with transaction.atomic():
                deleted_count, _ = Node.objects.filter(id__in=orphan_node_ids).delete()
                total_deleted += deleted_count
                logger.info(f"Deleted batch of {deleted_count} orphan nodes")
    
    if dry_run:
        # For dry run, count all orphan nodes
        total_orphans = Node.objects.filter(
            ways__isnull=True,
            station__isnull=True
        ).count()
        logger.info(f"Total orphan nodes found: {total_orphans} (dry run - not deleting)")
        return total_orphans
    else:
        logger.info(f"Total orphan nodes deleted: {total_deleted}")
        return total_deleted

def parse_osm_file(file_path, scope):
    logger.info(f"Starting to parse OSM file: {file_path}")
    logger.info(f"{'parsing' if scope[0] else 'skipping'} nodes, {'parsing' if scope[1] else 'skipping'} ways, {'parsing' if scope[2] else 'skipping'} relations")
    start_time = time.time()

    logger.info(f"Starting to apply OSM file to handler: {file_path}")
    start_time_handler = time.time()
    handler = OSMHandler(scope)
    handler.apply_file(file_path, locations=True)
    total_duration_handler = time.time() - start_time_handler
    logger.info(f"Applied OSM file to handler in {total_duration_handler:.4f} seconds")

    logger.info(f"OSM file has {len(handler.nodes) if handler.nodes is not None else 'N/A'} nodes, {len(handler.ways) if handler.ways is not None else 'N/A'} ways, {len(handler.relations) if handler.relations is not None else 'N/A'} relations, {len(handler.areas) if handler.areas is not None else 'N/A'} areas")
    
    # Process and save or update nodes
    if scope[0]:
        process_nodes(handler)

    # Process and save or update ways, aerialways, and pistes
    if scope[1]:
        process_ways(handler)
        delete_orphan_nodes_batch()

    # Process and save or update ski areas
    if scope[2]:
        process_relations(handler)

    if scope[3]:
        process_areas(handler)

    total_duration = time.time() - start_time
    logger.info(f"Finished parsing OSM file: {file_path} in {total_duration:.4f} seconds")

