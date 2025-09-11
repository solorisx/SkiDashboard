from django.db.models import Q
from .seasons import parse_season_string


def get_filter_query(request, season):
    """Build filter query for activities based on season parameter."""
    filter_query = Q()
    
    if season:
        start_date, end_date = parse_season_string(season)
        filter_query = Q(timestamp__range=(start_date, end_date))
    
    return filter_query


def get_user_activities_base_query(user):
    """Get base queryset for user activities with common optimizations."""
    from activities.models import Activity
    
    return (
        Activity.objects
        .filter(user=user)
        .select_related("ski_area")
        .prefetch_related("badges")
    )