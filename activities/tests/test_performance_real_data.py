import time
import sys
from django.test import TestCase
from django.contrib.gis.geos import Point
from django.conf import settings
from django.core.management import call_command

from activities.activity_parser import ActivityParser
from osm.models import Node, Station, Aerialway, SkiArea


class RealDataPerformanceTestCase(TestCase):
    """
    Performance tests using actual production data to identify real bottlenecks.
    These tests help measure the impact of optimizations on realistic data volumes.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Check if we're using a production database or test database
        db_name = settings.DATABASES['default']['NAME']
        is_test_db = 'test_' in db_name or db_name == ':memory:'
        keepdb_flag = '--keepdb' in sys.argv

        # Get counts of actual data
        cls.total_nodes = Node.objects.count()
        cls.total_stations = Station.objects.count()
        cls.total_aerialways = Aerialway.objects.count()
        cls.total_ski_areas = SkiArea.objects.count()

        # If we have very little data and we're in test mode with --keepdb, load OSM data
        if (cls.total_nodes < 10000 and cls.total_stations < 1000 and
            is_test_db and keepdb_flag):
            print("\n⚠️  Low data detected with --keepdb flag. Loading OSM data...")
            try:
                call_command('download_osm')
                print("✓ OSM data loaded successfully")
                # Refresh counts
                cls.total_nodes = Node.objects.count()
                cls.total_stations = Station.objects.count()
                cls.total_aerialways = Aerialway.objects.count()
                cls.total_ski_areas = SkiArea.objects.count()
                # Mark that we loaded OSM data
                cls.loaded_osm_data = True
            except Exception as e:
                print(f"✗ Failed to load OSM data: {e}")
                cls.loaded_osm_data = False
        elif not is_test_db:
            print("\n✓ Using production database - skipping OSM download")
            cls.loaded_osm_data = False
        elif is_test_db and not keepdb_flag:
            if cls.total_nodes > 1000:  # Likely has existing OSM data
                print(f"\n🚨 WARNING: Test database has {cls.total_nodes:,} nodes but --keepdb not used!")
                print("   This database will be DESTROYED after tests, losing all OSM data.")
                print("   Use --keepdb to preserve the data.")
            else:
                print("\n⚠️  Test database detected without --keepdb flag - OSM data would be lost")
            cls.loaded_osm_data = False
        
        print("\n=== Data Scale ===")
        print(f"Total Nodes: {cls.total_nodes:,}")
        print(f"Total Stations: {cls.total_stations:,}")
        print(f"Total Aerialways: {cls.total_aerialways:,}")
        print(f"Total Ski Areas: {cls.total_ski_areas:,}")
        
        # Get real ski areas with data for testing
        cls.test_ski_areas = list(SkiArea.objects.filter(
            ways__aerialway__isnull=False
        ).distinct()[:5])  # Top 5 ski areas with aerialways

        # Initialize test_points list
        cls.test_points = []

        if cls.test_ski_areas:
            for ski_area in cls.test_ski_areas[:3]:  # Use first 3 for performance testing
                if ski_area.geom:
                    centroid = ski_area.geom.centroid
                    cls.test_points.append(Point(centroid.x, centroid.y))
                    print(f"Test area: {ski_area.name} at {centroid}")
        
        if not cls.test_points:
            print("WARNING: No ski areas with geometry found for testing")
            # Fallback to multiple stations for pathfinding tests
            stations = Station.objects.filter(node__geom__isnull=False)[:5]
            if stations:
                cls.test_points = []
                for station in stations:
                    point = Point(station.node.geom.x, station.node.geom.y, srid=4326)
                    cls.test_points.append(point)
                    print(f"Using station: {station} at {point}")
            else:
                cls.test_points = []

    def setUp(self):
        # Create parser instance
        self.parser = ActivityParser()

        if not hasattr(self, 'test_points') or not self.test_points:
            self.skipTest("No real data available for performance testing")

    def test_build_lift_graph_real_data_performance(self):
        """Test graph building performance with real data scale"""
        if not self.test_points:
            self.skipTest("No test points available")
            
        test_point = self.test_points[0]
        
        print("\n=== Graph Building Performance (Real Data) ===")
        print(f"Test point: {test_point}")
        
        # Test different search areas to understand scaling
        search_areas = [1_000, 5_000, 10_000, 20_000]  # meters
        
        results = []
        
        for max_area in search_areas:
            print(f"\nTesting graph build with {max_area}m search radius...")
            
            # Count nearby stations first
            nearby_stations_count = Station.objects.filter(
                node__geom__distance_lte=(test_point, max_area)
            ).count()
            
            start_time = time.time()
            graph = self.parser.build_lift_graph(test_point, max_area=max_area, max_distance=500)
            build_time = time.time() - start_time
            
            result = {
                'search_radius': max_area,
                'nearby_stations': nearby_stations_count,
                'graph_stations': len(graph),
                'build_time': build_time,
                'stations_per_second': len(graph) / build_time if build_time > 0 else 0
            }
            results.append(result)
            
            print(f"  Nearby stations: {nearby_stations_count:,}")
            print(f"  Graph stations: {len(graph):,}")
            print(f"  Build time: {build_time:.4f}s")
            print(f"  Performance: {result['stations_per_second']:.1f} stations/sec")
            
            # Add reasonable timeout for very large areas
            if build_time > 120:  # 120 second timeout
                print(f"  TIMEOUT: Stopping at {max_area}m radius")
                break
        
        # Performance assertions
        if results:
            fastest_result = min(results, key=lambda x: x['build_time'])
            slowest_result = max(results, key=lambda x: x['build_time'])
            
            print("\n=== Performance Summary ===")
            print(f"Fastest: {fastest_result['build_time']:.4f}s for {fastest_result['graph_stations']} stations")
            print(f"Slowest: {slowest_result['build_time']:.4f}s for {slowest_result['graph_stations']} stations")
            
            # Flag potential performance issues
            if slowest_result['build_time'] > 5.0:
                print(f"⚠️  PERFORMANCE ISSUE: Graph building takes {slowest_result['build_time']:.2f}s")
                print("   This is too slow for real-time use")
            
            if slowest_result['stations_per_second'] < 100:
                print(f"⚠️  LOW THROUGHPUT: Only {slowest_result['stations_per_second']:.1f} stations/sec")

    def test_closest_aerialway_real_data_performance(self):
        """Test aerialway search performance with real data"""
        if not self.test_points:
            self.skipTest("No test points available")
            
        print("\n=== Closest Aerialway Performance (Real Data) ===")
        
        # Test multiple distances
        search_distances = [100, 500, 1000, 2500, 5000]  # meters
        
        for test_point in self.test_points[:2]:  # Test first 2 points
            print(f"\nTesting point: {test_point}")
            
            for max_distance in search_distances:
                start_time = time.time()
                aerialway = self.parser.get_closest_aerialway(test_point, max_distance=max_distance)
                query_time = time.time() - start_time
                
                print(f"  {max_distance}m search: {query_time:.4f}s -> {'Found' if aerialway else 'None'}")
                
                if query_time > 1.0:
                    print(f"  ⚠️  SLOW QUERY: {query_time:.4f}s is too slow for real-time use")

    def test_pathfinding_real_data_performance(self):
        """Test pathfinding performance between real locations"""
        if len(self.test_points) < 2:
            self.skipTest("Need at least 2 test points for pathfinding")
            
        print("\n=== Pathfinding Performance (Real Data) ===")
        
        start_point = self.test_points[0]
        end_point = self.test_points[1]
        
        print(f"Finding route from {start_point} to {end_point}")
        
        start_time = time.time()
        aerialways = self.parser.get_aerialways(start_point, end_point)
        pathfinding_time = time.time() - start_time
        
        print(f"Pathfinding completed in {pathfinding_time:.4f}s")
        print(f"Found {len(aerialways)} aerialways in route")
        
        if pathfinding_time > 10.0:
            print(f"⚠️  PATHFINDING TOO SLOW: {pathfinding_time:.4f}s")
            print("   This needs significant optimization")
        
        # Test if we can find any route at all with real data
        if aerialways:
            print(f"✅ Successfully found route with {len(aerialways)} lifts")
            for i, (aerialway, uphill) in enumerate(aerialways):
                direction = "⬆️ Uphill" if uphill else "⬇️ Downhill"
                print(f"  {i+1}. {aerialway.name} ({direction})")
        else:
            print("❌ No route found - may indicate data connectivity issues")

    def test_concurrent_graph_building_performance(self):
        """Test performance under concurrent load simulation"""
        if not self.test_points:
            self.skipTest("No test points available")
            
        print("\n=== Concurrent Performance Simulation ===")
        
        test_point = self.test_points[0]
        num_concurrent_requests = 5
        
        # Simulate multiple concurrent graph building requests
        start_time = time.time()
        
        graphs = []
        for i in range(num_concurrent_requests):
            print(f"Building graph {i+1}/{num_concurrent_requests}...")
            graph = self.parser.build_lift_graph(test_point, max_area=20000)
            graphs.append(graph)
        
        total_time = time.time() - start_time
        avg_time = total_time / num_concurrent_requests
        
        print(f"Total time for {num_concurrent_requests} graphs: {total_time:.4f}s")
        print(f"Average time per graph: {avg_time:.4f}s")
        print(f"Graphs per second: {num_concurrent_requests / total_time:.2f}")
        
        if avg_time > 2.0:
            print(f"⚠️  CONCURRENCY ISSUE: {avg_time:.4f}s per request is too slow")
            print("   Need caching to handle multiple concurrent users")

    def test_memory_usage_estimation(self):
        """Estimate memory usage of graph building"""
        if not self.test_points:
            self.skipTest("No test points available")
            
        print("\n=== Memory Usage Analysis ===")
        
        test_point = self.test_points[0]
        
        # Build a moderate-sized graph
        graph = self.parser.build_lift_graph(test_point, max_area=20000)
        
        # Estimate memory usage
        station_count = len(graph)
        connection_count = sum(len(connections) for connections in graph.values())
        
        # Rough memory estimation (bytes)
        # Each station object: ~1KB, each connection: ~100 bytes
        estimated_memory = (station_count * 1024) + (connection_count * 100)
        
        print("Graph contains:")
        print(f"  Stations: {station_count:,}")
        print(f"  Connections: {connection_count:,}")
        print(f"  Estimated memory: {estimated_memory / 1024 / 1024:.2f} MB")
        
        if estimated_memory > 50 * 1024 * 1024:  # 50MB
            print(f"⚠️  HIGH MEMORY USAGE: {estimated_memory / 1024 / 1024:.1f}MB per graph")
            print("   Caching strategy should consider memory limits")

    def test_database_query_analysis(self):
        """Analyze database query patterns during graph building"""
        print("\n=== Database Query Analysis ===")
        
        if not self.test_points:
            self.skipTest("No test points available")
            
        test_point = self.test_points[0]
        
        # Enable query logging for analysis
        from django.db import connection
        from django.conf import settings
        
        # Reset query log
        connection.queries_log.clear()
        
        start_time = time.time()
        graph = self.parser.build_lift_graph(test_point, max_area=20000)
        build_time = time.time() - start_time
        
        query_count = len(connection.queries)
        
        print("Graph building statistics:")
        print(f"  Build time: {build_time:.4f}s")
        print(f"  Database queries: {query_count}")
        print(f"  Queries per second: {query_count / build_time:.1f}")
        print(f"  Stations in graph: {len(graph)}")
        
        if query_count > 100:
            print(f"⚠️  HIGH QUERY COUNT: {query_count} queries")
            print("   Consider query optimization or eager loading")
        
        # Analyze query types
        if hasattr(settings, 'DEBUG') and settings.DEBUG:
            query_times = [float(q['time']) for q in connection.queries]
            if query_times:
                total_query_time = sum(query_times)
                slowest_query = max(query_times)
                
                print(f"  Total query time: {total_query_time:.4f}s")
                print(f"  Slowest query: {slowest_query:.4f}s")
                print(f"  Query efficiency: {(build_time - total_query_time) / build_time * 100:.1f}% non-DB time")