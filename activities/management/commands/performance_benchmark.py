from django.core.management.base import BaseCommand
from activities.tests.test_performance_real_data import RealDataPerformanceTestCase


class Command(BaseCommand):
    help = 'Run performance benchmarks using the test case code'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-graph',
            action='store_true',
            help='Skip expensive graph building tests',
        )
        parser.add_argument(
            '--skip-pathfinding',
            action='store_true',
            help='Skip pathfinding tests',
        )
        parser.add_argument(
            '--skip-concurrency',
            action='store_true',
            help='Skip concurrency performance tests',
        )
        parser.add_argument(
            '--skip-memory',
            action='store_true',
            help='Skip memory usage analysis',
        )
        parser.add_argument(
            '--skip-database',
            action='store_true',
            help='Skip database query analysis',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== Performance Benchmark ==='))

        # Create test instance and set it up
        test_case = RealDataPerformanceTestCase()

        test_case.setUpClass()

        # Check if we have test points
        if not hasattr(test_case, 'test_points') or not test_case.test_points:
            self.stdout.write(self.style.ERROR('No test points available for benchmarking'))
            return

        test_case.setUp()

        # Run the actual test methods
        try:
            if not options['skip_graph']:
                self.stdout.write('\n=== Running Graph Building Performance Test ===')
                test_case.test_build_lift_graph_real_data_performance()
            else:
                self.stdout.write(self.style.WARNING('\n⚠️  Skipping graph building tests'))

            self.stdout.write('\n=== Running Closest Aerialway Performance Test ===')
            test_case.test_closest_aerialway_real_data_performance()

            if not options['skip_pathfinding']:
                self.stdout.write('\n=== Running Pathfinding Performance Test ===')
                try:
                    test_case.test_pathfinding_real_data_performance()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Pathfinding test skipped: {e}'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠️  Skipping pathfinding tests'))

            if not options['skip_concurrency']:
                self.stdout.write('\n=== Running Concurrency Performance Test ===')
                try:
                    test_case.test_concurrent_graph_building_performance()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Concurrency test failed: {e}'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠️  Skipping concurrency tests'))

            if not options['skip_memory']:
                self.stdout.write('\n=== Running Memory Usage Analysis ===')
                try:
                    test_case.test_memory_usage_estimation()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Memory test failed: {e}'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠️  Skipping memory analysis'))

            if not options['skip_database']:
                self.stdout.write('\n=== Running Database Query Analysis ===')
                try:
                    test_case.test_database_query_analysis()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Database analysis failed: {e}'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠️  Skipping database analysis'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Test failed: {e}'))
            raise

        self.stdout.write(self.style.SUCCESS('\n✓ Performance benchmark completed'))