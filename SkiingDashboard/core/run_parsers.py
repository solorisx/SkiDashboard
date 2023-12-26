import os
import sys
import django
import argparse
from activity_parser import parse_fit_file
from osm_parser import parse_osm_file

sys.path.append('SkiingDashboard/SkiingDashboardApp')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SkiingDashboard/settings')
django.setup()