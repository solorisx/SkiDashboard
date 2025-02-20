import os
from django.core.management.base import BaseCommand, CommandError
from SkiingDashboard.core.test import test_strava, print_activities

class Command(BaseCommand):
    help = 'Tests the Strava interface'

    def add_arguments(self, parser):
        parser.add_argument(
            'action', nargs='?', default='test', choices=['test', 'print'],
            help="Specify 'test' to run test_strava or 'print' to run print_activities"
        )

    def handle(self, *args, **options):
        if options['action'] == 'print':
            print_activities()
        else:
            test_strava()