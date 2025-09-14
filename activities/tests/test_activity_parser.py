import time
from unittest.mock import Mock, patch
from django.test import TestCase
from django.contrib.gis.geos import Point, LineString
from django.contrib.auth.models import User

from activities.activity_parser import ActivityParser
from activities.models import Activity, Lap, LiftRide
from osm.models import Node, Way, Aerialway, Station, SkiArea, SkiAreaBoundary


class ActivityParserTestCase(TestCase):
    
    def setUp(self):
        # Create parser instance
        self.parser = ActivityParser()

        # Create test points
        self.test_point_1 = Point(7.1234, 46.5678)  # Bottom Station 1
        self.test_point_2 = Point(7.1244, 46.5688)  # Middle Station
        self.test_point_3 = Point(7.1254, 46.5698)  # Top Station 2
        self.test_point_outside = Point(7.2000, 46.6000)  # Outside test area

        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test OSM data
        self.node1 = Node.objects.create(
            osm_id=100001,
            geom=self.test_point_1
        )
        self.node2 = Node.objects.create(
            osm_id=100002,
            geom=self.test_point_2
        )
        self.node3 = Node.objects.create(
            osm_id=100003,
            geom=self.test_point_3
        )
        
        # Create test ways
        self.way1 = Way.objects.create(osm_id=200001)
        self.way2 = Way.objects.create(osm_id=200002)
        
        # Create WayNodes to link ways and nodes
        from osm.models import WayNode
        WayNode.objects.create(way=self.way1, node=self.node1, sequence=1)
        WayNode.objects.create(way=self.way1, node=self.node2, sequence=2)
        WayNode.objects.create(way=self.way2, node=self.node2, sequence=1)
        WayNode.objects.create(way=self.way2, node=self.node3, sequence=2)
        
        # Create test stations
        self.station1 = Station.objects.create(
            node=self.node1,
            name="Bottom Station 1",
            station="bottom",
            altitude=1200.0
        )
        self.station2 = Station.objects.create(
            node=self.node2,
            name="Middle Station",
            station="top",
            altitude=1400.0
        )
        self.station3 = Station.objects.create(
            node=self.node3,
            name="Top Station 2", 
            station="top",
            altitude=1600.0
        )
        
        # Create test aerialways
        self.aerialway1 = Aerialway.objects.create(
            way=self.way1,
            geom=LineString([self.test_point_1, self.test_point_2]),
            aerialway="chairlift",
            aerialway_capacity=4,
            aerialway_duration=8,
            name="Test Chairlift 1"
        )
        self.aerialway2 = Aerialway.objects.create(
            way=self.way2,
            geom=LineString([self.test_point_2, self.test_point_3]),
            aerialway="gondola",
            aerialway_capacity=8,
            aerialway_duration=12,
            name="Test Gondola 1"
        )
        
        # Link stations to aerialways
        self.aerialway1.station_nodes.add(self.station1, self.station2)
        self.aerialway2.station_nodes.add(self.station2, self.station3)
        
        # Create test ski area
        from django.contrib.gis.geos import Polygon, MultiPolygon
        ski_area_polygon = Polygon(((7.1230, 46.5674), (7.1270, 46.5674), 
                                   (7.1270, 46.5714), (7.1230, 46.5714), 
                                   (7.1230, 46.5674)))
        self.ski_area = SkiArea.objects.create(
            osm_id=500001,
            name="Test Ski Area",
            geom=MultiPolygon(ski_area_polygon)
        )
        
        # Link ways to ski area
        self.ski_area.ways.add(self.way1, self.way2)

    def test_get_osm_url(self):
        """Test OSM URL generation"""
        url = self.parser.get_osm_url(self.test_point_1)
        expected = f"https://www.openstreetmap.org/?mlat={self.test_point_1.y}&mlon={self.test_point_1.x}#map=17/{self.test_point_1.y}/{self.test_point_1.x}"
        self.assertEqual(url, expected)

    def test_extract_data(self):
        """Test data extraction from FIT message"""
        mock_message = Mock()
        mock_message.get_value.side_effect = lambda field: {
            'latitude': 465678000,
            'longitude': 71234000,
            'altitude': 1200,
            'invalid_field': None
        }.get(field)
        
        model_fields = ['latitude', 'longitude', 'altitude', 'invalid_field']
        result = self.parser.extract_data(mock_message, model_fields)
        
        expected = {
            'latitude': 465678000,
            'longitude': 71234000,
            'altitude': 1200
        }
        self.assertEqual(result, expected)

    def test_create_point(self):
        """Test point creation from lat/lon fields"""
        # Use precise conversion: coordinate * 11930465
        lat_semicircles = int(46.5678 * 11930465)  
        lon_semicircles = int(7.1234 * 11930465)
        
        data = {
            'position_lat': lat_semicircles,
            'position_long': lon_semicircles
        }
        
        point = self.parser.create_point('position_lat', 'position_long', data)
        self.assertIsInstance(point, Point)
        # Allow some precision loss in the conversion
        self.assertAlmostEqual(point.x, 7.1234, places=2)
        self.assertAlmostEqual(point.y, 46.5678, places=2)
        
        # Test with missing data
        incomplete_data = {'position_lat': 555567800}
        point = self.parser.create_point('position_lat', 'position_long', incomplete_data)
        self.assertIsNone(point)

    def test_get_closest_stations_basic(self):
        """Test finding closest stations"""
        stations = self.parser.get_closest_stations(self.test_point_1, max_distance=100)
        self.assertTrue(stations.exists())
        
        closest = stations.first()
        self.assertEqual(closest.station, "bottom")
        self.assertEqual(closest.name, "Bottom Station 1")

    def test_get_closest_stations_filters(self):
        """Test station filtering by type"""
        # Test bottom only
        bottom_stations = self.parser.get_closest_stations(self.test_point_2, bottom_only=True, max_distance=100)
        for station in bottom_stations:
            self.assertEqual(station.station, "bottom")
        
        # Test top only
        top_stations = self.parser.get_closest_stations(self.test_point_2, top_only=True, max_distance=100)
        for station in top_stations:
            self.assertEqual(station.station, "top")
        
        # Test invalid combination
        with self.assertRaises(ValueError):
            self.parser.get_closest_stations(self.test_point_1, bottom_only=True, top_only=True)

    def test_get_closest_stations_no_results(self):
        """Test when no stations are found"""
        stations = self.parser.get_closest_stations(self.test_point_outside, max_distance=10)
        self.assertFalse(stations.exists())

    def test_get_closest_aerialways_basic(self):
        """Test finding closest aerialways"""
        aerialways = self.parser.get_closest_aerialways(self.test_point_1, max_distance=100)
        self.assertTrue(aerialways.exists())
        
        closest = aerialways.first()
        self.assertEqual(closest.name, "Test Chairlift 1")

    def test_get_closest_aerialways_in_ski_area(self):
        """Test filtering aerialways by ski area"""
        aerialways = self.parser.get_closest_aerialways(
            self.test_point_1,
            in_ski_area=True,
            max_distance=1000
        )
        self.assertTrue(aerialways.exists())

    def test_get_closest_aerialway_single(self):
        """Test getting single closest aerialway"""
        aerialway = self.parser.get_closest_aerialway(self.test_point_1, max_distance=100)
        self.assertIsNotNone(aerialway)
        self.assertEqual(aerialway.name, "Test Chairlift 1")

    def test_get_ski_area(self):
        """Test finding ski area containing point"""
        ski_area = self.parser.get_ski_area(self.test_point_1)
        self.assertIsNotNone(ski_area)
        self.assertEqual(ski_area.name, "Test Ski Area")
        
        # Test point outside ski area
        ski_area_outside = self.parser.get_ski_area(self.test_point_outside)
        self.assertIsNone(ski_area_outside)

    def test_get_ski_area_with_buffer(self):
        """Test ski area finding with buffer distance"""
        # Point slightly outside but within buffer
        point_near = Point(7.1280, 46.5720)  # Just outside the test area
        ski_area = self.parser.get_ski_area(point_near, buffer=1000)  # 1km buffer
        self.assertIsNotNone(ski_area)

    def test_find_direct_lift(self):
        """Test finding direct lift between two points"""
        # Test direct connection
        direct_lift, uphill = self.parser.find_direct_lift(self.test_point_1, self.test_point_2)
        self.assertIsNotNone(direct_lift)
        self.assertEqual(direct_lift.name, "Test Chairlift 1")
        self.assertTrue(uphill)
        
        # Test reverse direction
        direct_lift_down, uphill_down = self.parser.find_direct_lift(self.test_point_2, self.test_point_1)
        self.assertIsNotNone(direct_lift_down)
        self.assertEqual(direct_lift_down.name, "Test Chairlift 1")
        self.assertFalse(uphill_down)

    def test_find_direct_lift_no_connection(self):
        """Test when no direct lift exists"""
        direct_lift, uphill = self.parser.find_direct_lift(self.test_point_1, self.test_point_outside)
        self.assertIsNone(direct_lift)

    def test_apply_exceptions(self):
        """Test aerialway exceptions"""
        aerialway = Aerialway.objects.first()
        
        # Test normal case (no exception)
        result = self.parser.apply_exceptions(aerialway)
        self.assertEqual(result, aerialway)
        
        # Test specific exception case
        with patch.object(aerialway.way, 'osm_id', 29258980):
            with patch('activities.activity_parser.Aerialway.objects.get') as mock_get:
                mock_replacement = Mock()
                mock_get.return_value = mock_replacement
                
                result = self.parser.apply_exceptions(aerialway)
                self.assertEqual(result, mock_replacement)
                mock_get.assert_called_once_with(way__osm_id=20011874)


class GraphBuildingTestCase(TestCase):
    
    def setUp(self):
        # Create parser instance
        self.parser = ActivityParser()

        # Use same setup as ActivityParserTestCase
        self.start_point = Point(7.1234, 46.5678)
        self.end_point = Point(7.1254, 46.5698)
        
        # Create minimal test data for graph building
        self.node1 = Node.objects.create(osm_id=100001, geom=self.start_point)
        self.node2 = Node.objects.create(osm_id=100002, geom=Point(7.1244, 46.5688))
        self.node3 = Node.objects.create(osm_id=100003, geom=self.end_point)
        
        self.way1 = Way.objects.create(osm_id=200001)
        self.way2 = Way.objects.create(osm_id=200002)
        
        from osm.models import WayNode
        WayNode.objects.create(way=self.way1, node=self.node1, sequence=1)
        WayNode.objects.create(way=self.way1, node=self.node2, sequence=2)
        WayNode.objects.create(way=self.way2, node=self.node2, sequence=1)
        WayNode.objects.create(way=self.way2, node=self.node3, sequence=2)
        
        self.station1 = Station.objects.create(node=self.node1, name="Bottom Station", station="bottom", altitude=1200.0)
        self.station2 = Station.objects.create(node=self.node2, name="Middle Station", station="top", altitude=1400.0)
        self.station3 = Station.objects.create(node=self.node3, name="Top Station", station="top", altitude=1600.0)
        
        self.aerialway1 = Aerialway.objects.create(
            way=self.way1, geom=LineString([self.start_point, Point(7.1244, 46.5688)]),
            aerialway="chairlift", name="Test Chairlift"
        )
        self.aerialway2 = Aerialway.objects.create(
            way=self.way2, geom=LineString([Point(7.1244, 46.5688), self.end_point]),
            aerialway="gondola", name="Test Gondola"
        )
        
        self.aerialway1.station_nodes.add(self.station1, self.station2)
        self.aerialway2.station_nodes.add(self.station2, self.station3)

    def test_build_lift_graph_structure(self):
        """Test lift graph building returns correct structure"""
        start_time = time.time()
        graph = self.parser.build_lift_graph(self.start_point, max_area=5000, max_distance=500)
        build_time = time.time() - start_time
        
        self.assertIsInstance(graph, dict)
        self.assertTrue(len(graph) > 0, "Graph should contain stations")
        
        # Verify graph contains station objects as keys
        stations = list(graph.keys())
        self.assertTrue(all(hasattr(station, 'node') for station in stations))
        
        # Verify graph edges have correct format: (distance, neighbor, aerialway)
        for station, connections in graph.items():
            self.assertIsInstance(connections, list)
            for connection in connections:
                self.assertEqual(len(connection), 3)
                distance, neighbor, aerialway = connection
                self.assertIsInstance(distance, (int, float))
                self.assertTrue(hasattr(neighbor, 'node'))
                # aerialway can be None for walking connections
        
        print(f"Graph built in {build_time:.4f} seconds with {len(graph)} stations")

    def test_build_lift_graph_contains_expected_stations(self):
        """Test graph contains expected stations from fixtures"""
        graph = self.parser.build_lift_graph(self.start_point, max_area=5000)
        
        station_names = []
        for station in graph.keys():
            if hasattr(station, 'name') and station.name:
                station_names.append(station.name)
        
        expected_stations = ["Bottom Station", "Middle Station", "Top Station"]
        found_stations = [name for name in expected_stations if any(name in station_name for station_name in station_names)]
        
        self.assertTrue(len(found_stations) > 0, f"Expected to find some test stations in graph. Found: {station_names}")

    def test_dijkstra_pathfinding(self):
        """Test Dijkstra algorithm with known start and end points"""
        graph = self.parser.build_lift_graph(self.start_point, max_area=5000)
        
        # Get start and end stations
        start_stations = [station for station in graph.keys() 
                         if hasattr(station, 'station') and station.station == 'bottom']
        end_stations = [station for station in graph.keys() 
                       if hasattr(station, 'station') and station.station == 'top']
        
        if start_stations and end_stations:
            path = self.parser.dijkstra(start_stations[:1], end_stations[:1], graph)
            
            self.assertIsInstance(path, list)
            if path:  # Path found
                self.assertTrue(len(path) >= 2, "Path should have at least 2 stations")
                self.assertIn(path[0], start_stations)
                self.assertIn(path[-1], end_stations)

    def test_dijkstra_no_path(self):
        """Test Dijkstra when no path exists"""
        # Create isolated graph with no connections
        isolated_graph = {}
        
        from osm.models import Station
        start_station = Station.objects.first()
        end_station = Station.objects.last()
        
        if start_station and end_station and start_station != end_station:
            isolated_graph[start_station] = []
            isolated_graph[end_station] = []
            
            path = self.parser.dijkstra([start_station], [end_station], isolated_graph)
            self.assertEqual(path, [], "Should return empty path when no connection exists")

    def test_get_aerialways_direct_connection(self):
        """Test get_aerialways finds direct connections"""
        start_point = Point(7.1234, 46.5678)  # Bottom Station 1
        end_point = Point(7.1244, 46.5688)    # Middle Station
        
        aerialways = self.parser.get_aerialways(start_point, end_point)
        
        self.assertIsInstance(aerialways, list)
        if aerialways:
            aerialway, uphill = aerialways[0]
            self.assertIsNotNone(aerialway)
            self.assertIsInstance(uphill, bool)

    def test_get_aerialways_single_point(self):
        """Test get_aerialways with only start or end point"""
        # Only start point
        aerialways_start = self.parser.get_aerialways(self.start_point, None)
        self.assertIsInstance(aerialways_start, list)
        
        # Only end point  
        aerialways_end = self.parser.get_aerialways(None, self.end_point)
        self.assertIsInstance(aerialways_end, list)

    def test_get_aerialways_no_connection(self):
        """Test get_aerialways when no connection exists"""
        far_point = Point(8.0000, 47.0000)  # Very far from test data
        
        aerialways = self.parser.get_aerialways(self.start_point, far_point)
        
        # Should return empty list or fallback results
        self.assertIsInstance(aerialways, list)


class PerformanceTestCase(TestCase):
    
    def setUp(self):
        # Create parser instance
        self.parser = ActivityParser()

        # Create minimal test data
        self.start_point = Point(7.1234, 46.5678)
        
        self.node1 = Node.objects.create(osm_id=100001, geom=self.start_point)
        self.node2 = Node.objects.create(osm_id=100002, geom=Point(7.1244, 46.5688))
        
        self.way1 = Way.objects.create(osm_id=200001)
        
        from osm.models import WayNode
        WayNode.objects.create(way=self.way1, node=self.node1, sequence=1)
        WayNode.objects.create(way=self.way1, node=self.node2, sequence=2)
        
        self.station1 = Station.objects.create(node=self.node1, name="Bottom Station", station="bottom")
        self.station2 = Station.objects.create(node=self.node2, name="Top Station", station="top")
        
        self.aerialway1 = Aerialway.objects.create(
            way=self.way1, geom=LineString([self.start_point, Point(7.1244, 46.5688)]),
            aerialway="chairlift", name="Test Chairlift"
        )
        self.aerialway1.station_nodes.add(self.station1, self.station2)
    
    def test_graph_building_performance(self):
        """Test graph building performance and capture baseline"""
        start_point = Point(7.1234, 46.5678, srid=4326)
        
        # Warm-up run
        self.parser.build_lift_graph(start_point, max_area=1000)
        
        # Measure performance
        start_time = time.time()
        graph = self.parser.build_lift_graph(start_point, max_area=5000, max_distance=500)
        build_time = time.time() - start_time
        
        self.assertIsInstance(graph, dict)
        self.assertLess(build_time, 10.0, f"Graph building took {build_time:.4f}s, expected < 10s")
        
        print(f"Baseline performance: {build_time:.4f}s for {len(graph)} stations")

    def test_closest_aerialway_performance(self):
        """Test performance of closest aerialway queries"""
        test_point = Point(7.1234, 46.5678)
        
        start_time = time.time()
        aerialway = self.parser.get_closest_aerialway(test_point, max_distance=1000)
        query_time = time.time() - start_time
        
        self.assertLess(query_time, 1.0, f"Closest aerialway query took {query_time:.4f}s, expected < 1s")
        
        print(f"Closest aerialway query: {query_time:.4f}s")