"""
Activities views module - refactored into smaller, focused modules.

This module now serves as the main entry point that imports views from
specialized modules to maintain backward compatibility.
"""

# Import views from specialized modules
from .activity import (
    activity_detail,
    activity_detail_strava,
    activity_list,
    get_unique_lift_rides,
    segment_map,
)

from .api import (
    home_stats as home_stats_data,
    season_stats,
)

from .statistics import (
    activity_list_skiarea,
    activity_list_skiarea_detail,
    lift_ride_list,
    lift_ride_list_season,
)

from .sync import (
    reprocess_activity,
    reset_all,
    sync_reprocess_all,
    sync_strava,
    sync_strava_admin,
    sync_strava_all,
)

from .webhook import (
    strava_webhook,
    subscribe_strava_webhook,
)

from .admin_profiling import (
    activity_profiling_dashboard,
    activity_profiling_detail,
)

# For backward compatibility, we also need to ensure the home_stats view 
# returns a proper HttpResponse for template rendering
from django.shortcuts import render

def home_stats(request):
    """Wrapper for home_stats to return proper template response."""
    context = home_stats_data(request)
    return render(request, "home.html", context)

# Export all views for URL configuration
__all__ = [
    # Activity views
    'activity_detail',
    'activity_detail_strava', 
    'activity_list',
    'get_unique_lift_rides',
    'segment_map',
    
    # API views
    'home_stats',
    'season_stats',
    
    # Statistics views
    'activity_list_skiarea',
    'activity_list_skiarea_detail',
    'lift_ride_list',
    'lift_ride_list_season',
    
    # Sync views
    'reprocess_activity',
    'reset_all',
    'sync_reprocess_all',
    'sync_strava',
    'sync_strava_admin',
    'sync_strava_all',
    
    # Webhook views
    'strava_webhook',
    'subscribe_strava_webhook',

    # Admin profiling views
    'activity_profiling_dashboard',
    'activity_profiling_detail',
]