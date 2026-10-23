from django.db.models import Q, Prefetch
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
    from django.db.models import Count
    from activities.models import Activity, ActivityBadge

    return (
        Activity.objects.filter(user=user)
        .select_related("ski_area", "user", "user__userprofile")
        .prefetch_related(
            Prefetch("badges", queryset=ActivityBadge.objects.select_related("badge").order_by("badge__sort_key"))
        )
        .annotate(badge_count=Count("badges"))
    )
