import os
from django.core.management.base import BaseCommand, CommandError
from SkiingDashboard.core.test import test_strava

class Command(BaseCommand):
    help = 'Tests the Strava interface'

    def handle(self, *args, **options):
        test_strava()