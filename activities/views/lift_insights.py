import json
import logging
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncWeek
from django.shortcuts import render
from django.http import JsonResponse
from django.core.cache import cache

from ..models import LiftRide, Activity
from ..utils.completeness import (
    calculate_ski_area_completeness,
    get_available_lifts_in_ski_area
)
from ..utils.queries import get_filter_query, get_user_activities_base_query
from ..utils.seasons import get_seasons
from core.premium import filter_seasons_for_user, premium_season_required
from osm.models import SkiArea

logger = logging.getLogger(__name__)


@login_required
@premium_season_required
def lift_insights(request, season=None):
    """Show comprehensive lift ride insights and completeness statistics."""

    # Get season filter
    filter_query = get_filter_query(request, season)
    activities = get_user_activities_base_query(request.user).filter(filter_query)
    seasons = filter_seasons_for_user(get_seasons(user=request.user), request.user)

    # Recent lift rides with context
    recent_rides = LiftRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).select_related(
        'aerialway', 'lap__activity', 'lap__activity__ski_area'
    ).order_by('-timestamp')[:5]

    # Personal records
    # Most rides on a single lift (season-filtered)
    most_ridden_lift_ever = LiftRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).values(
        'aerialway__name', 'aerialway__id'
    ).annotate(
        ride_count=Count('id')
    ).order_by('-ride_count').first()

    # Most rides on a single lift in one day
    most_rides_single_day = activities.aggregate(
        max_lifts=Max('num_lift_rides')
    )
    best_single_day_activity = None
    if most_rides_single_day['max_lifts']:
        best_single_day_activity = activities.filter(
            num_lift_rides=most_rides_single_day['max_lifts']
        ).first()

    # Most unique lifts in one day
    activities_with_unique_lifts = []
    for activity in activities.filter(num_lift_rides__gt=0)[:50]:  # Limit for performance
        unique_lifts_count = LiftRide.objects.filter(
            lap__activity=activity
        ).values('aerialway').distinct().count()
        activities_with_unique_lifts.append((activity, unique_lifts_count))

    # Sort by unique lifts count
    activities_with_unique_lifts.sort(key=lambda x: x[1], reverse=True)
    most_unique_lifts_day = activities_with_unique_lifts[0] if activities_with_unique_lifts else None

    # Overall completeness statistics (season-filtered)
    # Get ski areas from filtered activities for season-specific completeness
    season_ski_areas = SkiArea.objects.filter(
        activity__in=activities
    ).distinct()

    # Calculate overall completeness based on season-filtered ski areas
    if season_ski_areas.exists():
        overall_completeness = {
            'total_ski_areas': season_ski_areas.count(),
            'overall_percentage': 0  # We'll calculate this if needed
        }
        # If we need detailed overall percentage, we'd need to calculate it
        # by iterating through season_ski_areas and calling calculate_ski_area_completeness
        # But for now, just provide the count
    else:
        overall_completeness = {
            'total_ski_areas': 0,
            'overall_percentage': 0
        }

    # Top ski areas by completeness
    ski_area_completeness = []

    # Get all visited ski areas first to get total count (filtered by season)
    all_visited_ski_areas = SkiArea.objects.filter(
        activity__user=request.user
    ).filter(activity__in=activities).distinct()

    # Get total count for "View All" button logic
    total_ski_areas_count = all_visited_ski_areas.count()

    # Limit to first 10 for performance in main display
    visited_ski_areas = all_visited_ski_areas[:10]

    for ski_area in visited_ski_areas:
        completeness = calculate_ski_area_completeness(request.user, ski_area, season=season)

        # Get number of visits (activities) for this ski area
        visit_count_query = Activity.objects.filter(
            user=request.user,
            ski_area=ski_area
        )
        if season:
            visit_count_query = visit_count_query.filter(filter_query)
        visit_count = visit_count_query.count()

        ski_area_completeness.append({
            'ski_area': ski_area,
            'completeness': completeness,
            'visit_count': visit_count
        })

    # Sort by completion percentage
    ski_area_completeness.sort(key=lambda x: x['completeness']['completion_percentage'], reverse=True)

    # Lift type statistics
    lift_type_stats = LiftRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).values(
        'aerialway__aerialway'
    ).annotate(
        count=Count('id')
    ).order_by('-count')

    # Season-specific statistics
    season_stats = activities.aggregate(
        total_activities=Count('id'),
        total_lifts=Sum('num_lift_rides')
    )

    # Calculate unique lifts separately using LiftRide model
    unique_lifts = LiftRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).values('aerialway').distinct().count()

    season_stats['unique_lifts'] = unique_lifts

    # Handle None values
    for key in season_stats:
        if season_stats[key] is None:
            season_stats[key] = 0

    # Weekly lift rides trend for line chart
    weekly_lifts_raw = (
        LiftRide.objects.filter(lap__activity__user=request.user)
        .filter(filter_query)
        .annotate(week=TruncWeek('timestamp'))
        .values('week')
        .annotate(count=Count('id'))
        .order_by('week')
    )
    weekly_lifts = json.dumps([
        {'week': row['week'].strftime('%b %d'), 'count': row['count']}
        for row in weekly_lifts_raw if row['week']
    ])

    # Lift type breakdown for donut chart
    lift_type_chart = json.dumps([
        {
            'type': (row['aerialway__aerialway'] or 'unknown').replace('_', ' ').title(),
            'count': row['count'],
        }
        for row in lift_type_stats
    ])

    context = {
        'recent_rides': recent_rides,
        'most_ridden_lift_ever': most_ridden_lift_ever,
        'best_single_day_activity': best_single_day_activity,
        'most_unique_lifts_day': most_unique_lifts_day,
        'overall_completeness': overall_completeness,
        'ski_area_completeness': ski_area_completeness[:10],
        'total_ski_areas': total_ski_areas_count,
        'lift_type_stats': lift_type_stats,
        'lift_type_chart': lift_type_chart,
        'weekly_lifts': weekly_lifts,
        'season_stats': season_stats,
        'seasons': seasons,
        'selected_season': season,
    }

    return render(request, 'activities/lift_insights.html', context)


@login_required
@premium_season_required
def ski_area_completeness_detail(request, ski_area_id, season=None):
    """Show detailed completeness view for a specific ski area."""
    ski_area = SkiArea.objects.get(id=ski_area_id)

    # Get season filter
    filter_query = get_filter_query(request, season)
    seasons = filter_seasons_for_user(get_seasons(user=request.user), request.user)

    # Get all available lifts in this ski area (with user exclusions)
    available_lifts = get_available_lifts_in_ski_area(ski_area, user=request.user)

    # Calculate completeness for this ski area (with season filtering)
    completeness = calculate_ski_area_completeness(request.user, ski_area, season=season)

    # Calculate piste completeness for this ski area
    from .piste_insights import get_available_pistes_in_ski_area
    from ..utils.completeness import calculate_ski_area_piste_completeness
    piste_completeness = calculate_ski_area_piste_completeness(request.user, ski_area, season=season)

    # Get lifts the user has ridden with additional stats
    user_lift_rides = LiftRide.objects.filter(
        lap__activity__user=request.user,
        lap__activity__ski_area=ski_area,
        aerialway__in=available_lifts
    )

    if season:
        user_lift_rides = user_lift_rides.filter(filter_query)

    # Get ridden lifts with stats
    ridden_lift_stats = user_lift_rides.values(
        'aerialway__id',
        'aerialway__name',
        'aerialway__aerialway',
    ).annotate(
        total_rides=Count('id'),
        first_ride=Min('timestamp'),
        last_ride=Max('timestamp'),
        unique_days=Count('lap__activity__timestamp__date', distinct=True)
    ).order_by('-total_rides', 'aerialway__name')

    # Get aerialway objects for ridden lifts
    ridden_aerialway_ids = [stat['aerialway__id'] for stat in ridden_lift_stats]
    ridden_lifts = available_lifts.filter(id__in=ridden_aerialway_ids)

    # Create lookup for stats
    stats_lookup = {stat['aerialway__id']: stat for stat in ridden_lift_stats}

    # Combine lift objects with stats
    ridden_lifts_with_stats = []
    for lift in ridden_lifts:
        lift_data = stats_lookup[lift.id]
        ridden_lifts_with_stats.append({
            'lift': lift,
            'total_rides': lift_data['total_rides'],
            'first_ride': lift_data['first_ride'],
            'last_ride': lift_data['last_ride'],
            'unique_days': lift_data['unique_days']
        })

    # Sort by total rides descending
    ridden_lifts_with_stats.sort(key=lambda x: x['total_rides'], reverse=True)

    # Get not ridden lifts
    not_ridden_lifts = available_lifts.exclude(id__in=ridden_aerialway_ids).order_by('name')

    # Get recent activities in this ski area
    recent_activities_query = Activity.objects.filter(
        user=request.user,
        ski_area=ski_area
    )

    if season:
        recent_activities_query = recent_activities_query.filter(filter_query)

    # Get total visit count for this ski area
    total_visits = recent_activities_query.count()

    recent_activities = recent_activities_query.order_by('-timestamp')[:10]

    context = {
        'ski_area': ski_area,
        'completeness': completeness,
        'piste_completeness': piste_completeness,
        'ridden_lifts_with_stats': ridden_lifts_with_stats,
        'not_ridden_lifts': not_ridden_lifts,
        'recent_activities': recent_activities,
        'total_visits': total_visits,
        'seasons': seasons,
        'selected_season': season,
    }

    return render(request, 'activities/ski_area_completeness_detail.html', context)


@login_required
@premium_season_required
def ski_area_completeness_all(request, season=None):
    """Show completeness for all ski areas."""
    # Get season filter
    seasons = filter_seasons_for_user(get_seasons(user=request.user), request.user)

    # Get all ski areas by completeness
    ski_area_completeness = []
    visited_ski_areas = SkiArea.objects.filter(
        activity__user=request.user
    ).distinct()

    for ski_area in visited_ski_areas:
        completeness = calculate_ski_area_completeness(request.user, ski_area, season=season)

        # Get number of visits (activities) for this ski area
        visit_count_query = Activity.objects.filter(
            user=request.user,
            ski_area=ski_area
        )
        if season:
            from ..utils.queries import get_filter_query
            filter_query = get_filter_query(request, season)
            visit_count_query = visit_count_query.filter(filter_query)
        visit_count = visit_count_query.count()

        ski_area_completeness.append({
            'ski_area': ski_area,
            'completeness': completeness,
            'visit_count': visit_count
        })

    # Sort by completion percentage
    ski_area_completeness.sort(key=lambda x: x['completeness']['completion_percentage'], reverse=True)

    context = {
        'ski_area_completeness': ski_area_completeness,
        'seasons': seasons,
        'selected_season': season,
        'page_title': 'All Ski Area Completeness'
    }

    return render(request, 'activities/ski_area_completeness_all.html', context)


@login_required
def reload_ski_area_completeness(request, ski_area_id):
    """API endpoint to reload/refresh ski area completeness data."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'AJAX requests only'}, status=400)

    try:
        ski_area = SkiArea.objects.get(id=ski_area_id)

        # Get season from request if provided
        season = request.GET.get('season')

        # Clear cache for this ski area completeness
        cache_key = f"completeness_{request.user.id}_{ski_area.id}"
        if season:
            cache_key += f"_{season}"
        cache.delete(cache_key)

        # Recalculate with force_calc=True
        completeness = calculate_ski_area_completeness(request.user, ski_area, force_calc=True, season=season)

        return JsonResponse({
            'success': True,
            'message': 'Completeness data refreshed successfully',
            'completeness': completeness
        })

    except SkiArea.DoesNotExist:
        return JsonResponse({'error': 'Ski area not found'}, status=404)
    except Exception as e:
        logger.error(f"Error reloading completeness for ski area {ski_area_id}: {e}")
        return JsonResponse({'error': 'Error refreshing completeness data'}, status=500)