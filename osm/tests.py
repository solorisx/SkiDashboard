import tempfile
import os
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.contrib.gis.geos import Point, LineString
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Node, Way, WayNode, Aerialway, Piste, Station, SkiArea, SkiAreaBoundary
from .osm_parser import (
    OSMHandler, duration_to_minutes, ele_to_float, str_to_int,
    process_nodes, process_ways, process_areas, process_relations,
    delete_orphan_nodes, delete_orphan_nodes_batch, parse_osm_file
)
from .tasks import parse_osm_file_task


class OSMUtilityFunctionsTest(TestCase):
    """Test utility functions in osm_parser.py"""

    def test_duration_to_minutes_valid(self):
        """Test duration_to_minutes with valid input"""
        self.assertEqual(duration_to_minutes("15:30"), 15)
        self.assertEqual(duration_to_minutes("5:45"), 5)
        self.assertEqual(duration_to_minutes("120:00"), 120)

    def test_duration_to_minutes_invalid(self):
        """Test duration_to_minutes with invalid input"""
        self.assertIsNone(duration_to_minutes("invalid"))
        self.assertIsNone(duration_to_minutes(""))
        self.assertIsNone(duration_to_minutes(None))

    def test_ele_to_float_valid(self):
        """Test ele_to_float with valid input"""
        self.assertEqual(ele_to_float("1234.56m"), 1234.56)
        self.assertEqual(ele_to_float("500m"), 500.0)
        self.assertEqual(ele_to_float("1000"), 1000.0)

    def test_ele_to_float_invalid(self):
        """Test ele_to_float with invalid input"""
        self.assertIsNone(ele_to_float("invalid"))
        self.assertIsNone(ele_to_float(""))
        self.assertIsNone(ele_to_float(None))

    def test_str_to_int_valid(self):
        """Test str_to_int with valid input"""
        self.assertEqual(str_to_int("123"), 123)
        self.assertEqual(str_to_int("0"), 0)
        self.assertEqual(str_to_int("-45"), -45)

    def test_str_to_int_invalid(self):
        """Test str_to_int with invalid input"""
        self.assertIsNone(str_to_int("invalid"))
        self.assertIsNone(str_to_int("12.34"))
        self.assertIsNone(str_to_int(""))
        self.assertIsNone(str_to_int(None))


class OSMHandlerTest(TestCase):
    """Test OSMHandler class"""

    def setUp(self):
        """Set up test fixtures"""
        self.scope_all = (True, True, True, True)  # nodes, ways, relations, areas
        self.scope_nodes_only = (True, False, False, False)
        self.scope_ways_only = (False, True, False, False)

    def test_handler_initialization_all_scope(self):
        """Test handler initialization with all scope enabled"""
        handler = OSMHandler(self.scope_all)
        self.assertIsNotNone(handler.nodes)
        self.assertIsNotNone(handler.ways)
        self.assertIsNotNone(handler.relations)
        self.assertIsNotNone(handler.areas)
        self.assertEqual(handler.processed_count, 0)

    def test_handler_initialization_selective_scope(self):
        """Test handler initialization with selective scope"""
        handler = OSMHandler(self.scope_nodes_only)
        self.assertIsNotNone(handler.nodes)
        self.assertIsNone(handler.ways)
        self.assertIsNone(handler.relations)
        self.assertIsNone(handler.areas)

    def test_node_processing(self):
        """Test node processing"""
        handler = OSMHandler(self.scope_nodes_only)

        # Mock node object
        mock_node = MagicMock()
        mock_node.id = 12345
        mock_node.location.lon = 8.5
        mock_node.location.lat = 47.5
        mock_node.tags = {'name': 'Test Node'}

        handler.node(mock_node)

        self.assertEqual(len(handler.nodes), 1)
        node_data = handler.nodes[0]
        self.assertEqual(node_data['osm_id'], 12345)
        self.assertEqual(node_data['geom'], 'POINT(8.5 47.5)')
        self.assertEqual(node_data['tags'], {'name': 'Test Node'})

    def test_way_processing(self):
        """Test way processing"""
        handler = OSMHandler(self.scope_ways_only)

        # Mock way object
        mock_way = MagicMock()
        mock_way.id = 67890
        mock_way.tags = {'highway': 'primary'}
        mock_way.nodes = [MagicMock(ref=1), MagicMock(ref=2), MagicMock(ref=3)]

        # Mock wkbfab for geometry creation
        with patch('osm.osm_parser.wkbfab') as mock_wkbfab:
            mock_wkbfab.create_linestring.return_value = 'LINESTRING(0 0, 1 1)'
            handler.way(mock_way)

        self.assertEqual(len(handler.ways), 1)
        way_data = handler.ways[0]
        self.assertEqual(way_data['osm_id'], 67890)
        self.assertEqual(way_data['nodes'], [1, 2, 3])
        self.assertEqual(way_data['tags'], {'highway': 'primary'})


class NodeModelTest(TransactionTestCase):
    """Test Node model and processing"""

    def setUp(self):
        """Set up test data"""
        self.node_data = {
            'osm_id': 12345,
            'geom': Point(8.5, 47.5),
            'tags': {'name': 'Test Node', 'amenity': 'restaurant'}
        }

    def test_node_creation(self):
        """Test creating a node"""
        node = Node.objects.create(**self.node_data)
        self.assertEqual(node.osm_id, 12345)
        self.assertEqual(node.geom.x, 8.5)
        self.assertEqual(node.geom.y, 47.5)
        self.assertEqual(node.tags['name'], 'Test Node')

    def test_node_string_representation(self):
        """Test node string representation"""
        node = Node.objects.create(**self.node_data)
        self.assertEqual(str(node), "Node 12345")

    def test_get_osm_url(self):
        """Test OSM URL generation"""
        node = Node.objects.create(**self.node_data)
        expected_url = "https://www.openstreetmap.org/node/12345"
        self.assertEqual(node.get_osm_url(), expected_url)


class ProcessNodesTest(TransactionTestCase):
    """Test process_nodes function"""

    def setUp(self):
        """Set up test handler with sample nodes"""
        self.handler = OSMHandler((True, False, False, False))
        # Add sample nodes
        for i in range(5):
            self.handler.nodes.append({
                'osm_id': 1000 + i,
                'geom': f'POINT({8.5 + i * 0.1} {47.5 + i * 0.1})',
                'tags': {'name': f'Test Node {i}'}
            })

    def test_process_nodes_success(self):
        """Test successful node processing"""
        initial_count = Node.objects.count()
        process_nodes(self.handler)

        self.assertEqual(Node.objects.count(), initial_count + 5)

        # Check first node
        node = Node.objects.get(osm_id=1000)
        self.assertEqual(node.tags['name'], 'Test Node 0')

    def test_process_nodes_empty_handler(self):
        """Test processing with empty handler"""
        empty_handler = OSMHandler((True, False, False, False))
        empty_handler.nodes = []

        initial_count = Node.objects.count()
        process_nodes(empty_handler)
        self.assertEqual(Node.objects.count(), initial_count)


class OrphanNodeCleanupTest(TransactionTestCase):
    """Test orphan node cleanup functions"""

    def setUp(self):
        """Create test nodes, some orphaned"""
        # Create orphaned nodes
        self.orphan1 = Node.objects.create(
            osm_id=1001,
            geom=Point(8.5, 47.5),
            tags={}
        )
        self.orphan2 = Node.objects.create(
            osm_id=1002,
            geom=Point(8.6, 47.6),
            tags={}
        )

        # Create node with way relationship
        self.connected_node = Node.objects.create(
            osm_id=1003,
            geom=Point(8.7, 47.7),
            tags={}
        )
        self.way = Way.objects.create(osm_id=2001, tags={})
        WayNode.objects.create(way=self.way, node=self.connected_node, sequence=1)

    def test_delete_orphan_nodes_dry_run(self):
        """Test orphan node detection in dry run mode"""
        orphan_count = delete_orphan_nodes(dry_run=True)
        self.assertEqual(orphan_count, 2)  # Only orphan1 and orphan2

        # Ensure no nodes were actually deleted
        self.assertTrue(Node.objects.filter(osm_id=1001).exists())
        self.assertTrue(Node.objects.filter(osm_id=1002).exists())

    def test_delete_orphan_nodes_actual_deletion(self):
        """Test actual orphan node deletion"""
        initial_count = Node.objects.count()
        orphan_count = delete_orphan_nodes(dry_run=False)

        self.assertEqual(orphan_count, 2)
        self.assertEqual(Node.objects.count(), initial_count - 2)

        # Ensure only orphaned nodes were deleted
        self.assertFalse(Node.objects.filter(osm_id=1001).exists())
        self.assertFalse(Node.objects.filter(osm_id=1002).exists())
        self.assertTrue(Node.objects.filter(osm_id=1003).exists())

    def test_delete_orphan_nodes_batch(self):
        """Test batch orphan node deletion"""
        orphan_count = delete_orphan_nodes_batch(batch_size=1, dry_run=False)
        self.assertEqual(orphan_count, 2)


class MockOSMFileTest(TestCase):
    """Test OSM file parsing with mocked osmium"""

    def test_parse_osm_file_error_handling(self):
        """Test error handling in parse_osm_file"""
        with tempfile.NamedTemporaryFile(suffix='.osm', delete=False) as tmp_file:
            tmp_file.write(b'<osm></osm>')
            tmp_file_path = tmp_file.name

        try:
            # Test with invalid scope
            with patch('osm.osm_parser.OSMHandler') as mock_handler_class:
                mock_handler = MagicMock()
                mock_handler.nodes = []
                mock_handler.ways = []
                mock_handler.relations = []
                mock_handler.areas = []
                mock_handler_class.return_value = mock_handler

                # Should not raise exception
                parse_osm_file(tmp_file_path, (True, False, False, False))

                mock_handler_class.assert_called_once()
                mock_handler.apply_file.assert_called_once()
        finally:
            os.unlink(tmp_file_path)


class CeleryTaskTest(TestCase):
    """Test Celery tasks"""

    @patch('osm.tasks.load_osm')
    @patch('osm.tasks.parse_osm_file')
    def test_parse_osm_file_task_success(self, mock_parse, mock_load):
        """Test successful task execution"""
        mock_load.return_value = None
        mock_parse.return_value = None

        # Execute task
        result = parse_osm_file_task('/path/to/file.osm', (True, False, False, False))

        mock_load.assert_called_once()
        mock_parse.assert_called_once_with('/path/to/file.osm', (True, False, False, False))

    @patch('osm.tasks.load_osm')
    @patch('osm.tasks.parse_osm_file')
    def test_parse_osm_file_task_error(self, mock_parse, mock_load):
        """Test task error handling"""
        mock_load.return_value = None
        mock_parse.side_effect = Exception("Parse error")

        with self.assertRaises(Exception):
            parse_osm_file_task('/path/to/file.osm', (True, False, False, False))


class WayGeometryTest(TransactionTestCase):
    """Test Way model geometry construction"""

    def setUp(self):
        """Create test way with nodes"""
        self.way = Way.objects.create(osm_id=3001, tags={})

        # Create nodes
        self.nodes = []
        for i in range(3):
            node = Node.objects.create(
                osm_id=2001 + i,
                geom=Point(8.5 + i * 0.1, 47.5 + i * 0.1),
                tags={}
            )
            self.nodes.append(node)
            WayNode.objects.create(way=self.way, node=node, sequence=i)

    def test_constructed_geom_linestring(self):
        """Test linestring geometry construction"""
        geom = self.way.constructed_geom
        self.assertIsNotNone(geom)
        self.assertEqual(geom.geom_type, 'LineString')
        self.assertEqual(len(geom.coords), 3)

    def test_constructed_geom_insufficient_nodes(self):
        """Test geometry construction with insufficient nodes"""
        # Create way with only one node
        single_node_way = Way.objects.create(osm_id=3002, tags={})
        node = Node.objects.create(osm_id=2010, geom=Point(8.5, 47.5), tags={})
        WayNode.objects.create(way=single_node_way, node=node, sequence=0)

        geom = single_node_way.constructed_geom
        self.assertIsNone(geom)


class ErrorHandlingTest(TestCase):
    """Test error handling throughout the codebase"""

    def test_utility_functions_handle_none_input(self):
        """Test that utility functions handle None input gracefully"""
        self.assertIsNone(duration_to_minutes(None))
        self.assertIsNone(ele_to_float(None))
        self.assertIsNone(str_to_int(None))

    def test_utility_functions_handle_empty_string(self):
        """Test that utility functions handle empty strings gracefully"""
        self.assertIsNone(duration_to_minutes(""))
        self.assertIsNone(ele_to_float(""))
        self.assertIsNone(str_to_int(""))


class MemoryEfficiencyTest(TestCase):
    """Test memory efficiency improvements"""

    def test_handler_scope_memory_optimization(self):
        """Test that handlers with limited scope use less memory"""
        # Handler with all scope
        handler_all = OSMHandler((True, True, True, True))

        # Handler with limited scope
        handler_limited = OSMHandler((True, False, False, False))

        # Check that limited handler doesn't allocate unnecessary lists
        self.assertIsNotNone(handler_all.nodes)
        self.assertIsNotNone(handler_all.ways)
        self.assertIsNotNone(handler_all.relations)
        self.assertIsNotNone(handler_all.areas)

        self.assertIsNotNone(handler_limited.nodes)
        self.assertIsNone(handler_limited.ways)
        self.assertIsNone(handler_limited.relations)
        self.assertIsNone(handler_limited.areas)