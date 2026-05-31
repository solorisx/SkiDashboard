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
    activity_map,
    get_unique_lift_rides,
    segment_map,
    ActivityAPI,
    generate_share_image,
)

from .api import (
    activity_completeness_api,
    activity_completeness_batch_api,
    activity_piste_completeness_api,
    activity_piste_completeness_batch_api,
    home_stats as home_stats_data,
    season_stats,
    update_strava_description_api,
)

from .statistics import (
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

from .insights import (
    activity_insights,
    generate_season_share_image_view,
)

from .lift_insights import (
    lift_insights,
    ski_area_completeness_detail,
    ski_area_completeness_all,
    reload_ski_area_completeness,
)

from .piste_insights import (
    piste_insights,
    ski_area_piste_completeness_detail,
    ski_area_piste_completeness_all,
    reload_ski_area_piste_completeness,
)

from .trips import (
    trip_list,
    trip_detail,
    rename_trip,
    recluster_trips,
)

from .summer import (
    summer_activity_list,
    summer_activity_create,
    summer_activity_edit,
    summer_activity_delete,
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
    'activity_map',
    'get_unique_lift_rides',
    'segment_map',
    'ActivityAPI',
    'generate_share_image',
    
    # API views
    'activity_completeness_api',
    'activity_completeness_batch_api',
    'activity_piste_completeness_api',
    'activity_piste_completeness_batch_api',
    'home_stats',
    'season_stats',
    'update_strava_description_api',
    
    # Statistics views
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

    # Insights views
    'activity_insights',
    'generate_season_share_image_view',
    'lift_insights',
    'ski_area_completeness_detail',
    'ski_area_completeness_all',
    'reload_ski_area_completeness',

    # Piste insights views
    'piste_insights',
    'ski_area_piste_completeness_detail',
    'ski_area_piste_completeness_all',
    'reload_ski_area_piste_completeness',

    # Trip views
    'trip_list',
    'trip_detail',
    'rename_trip',
    'recluster_trips',

    # Summer activity views
    'summer_activity_list',
    'summer_activity_create',
    'summer_activity_edit',
    'summer_activity_delete',
]