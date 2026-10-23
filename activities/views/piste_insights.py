import json
import logging
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Min, Sum
from django.shortcuts import render
from django.http import JsonResponse
from django.core.cache import cache

from ..models import PisteRide, Activity
from ..utils.completeness import (
    calculate_ski_area_piste_completeness,
    get_available_pistes_in_ski_area
)
from ..utils.queries import get_filter_query, get_user_activities_base_query
from ..utils.seasons import get_seasons
from core.premium import filter_seasons_for_user, premium_season_required
from osm.models import SkiArea, Piste

logger = logging.getLogger(__name__)


@login_required
@premium_season_required
def piste_insights(request, season=None):
    """Show comprehensive piste ride insights and completeness statistics."""

    # Get season filter
    filter_query = get_filter_query(request, season)
    activities = get_user_activities_base_query(request.user).filter(filter_query)
    seasons = filter_seasons_for_user(get_seasons(user=request.user), request.user)

    # Recent piste rides with context
    recent_rides = PisteRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).select_related(
        'piste', 'lap__activity', 'lap__activity__ski_area'
    ).order_by('-timestamp')[:5]

    # Add length to recent rides
    for ride in recent_rides:
        if ride.piste.length:
            ride.length_meters = int(ride.piste.length)
        else:
            ride.length_meters = None

    # Personal records
    # Most rides on a single piste (season-filtered, only pistes over 100m)
    most_ridden_piste_stats = PisteRide.objects.filter(
        lap__activity__user=request.user,
        piste__length__gt=1000  # Only pistes over 1000m
    ).filter(filter_query).values(
        'piste__name', 'piste__id'
    ).annotate(
        ride_count=Count('id')
    ).order_by('-ride_count').first()

    # Get the actual Piste object if we found a most ridden piste
    most_ridden_piste_ever = None
    if most_ridden_piste_stats:
        try:
            piste = Piste.objects.select_related('way').get(id=most_ridden_piste_stats['piste__id'])
            most_ridden_piste_ever = {
                'piste': piste,
                'piste__name': most_ridden_piste_stats['piste__name'],
                'ride_count': most_ridden_piste_stats['ride_count']
            }
        except Piste.DoesNotExist:
            logger.warning(f"Piste {most_ridden_piste_stats['piste__id']} not found")

    # Most ridden piste by total distance (ride_count * piste_length, only pistes over 100m)
    # Calculate total distance and get the Piste object
    most_distance_piste_ever = None
    # Get all pistes with length over 100m and calculate total distance
    pistes_by_distance = PisteRide.objects.filter(
        lap__activity__user=request.user,
        piste__length__gt=1000  # Only pistes over 1000m
    ).filter(filter_query).values(
        'piste__id', 'piste__name', 'piste__length'
    ).annotate(
        ride_count=Count('id')
    )

    if pistes_by_distance.exists():
        # Calculate total distance for each piste
        pistes_with_total_distance = []
        for piste_stat in pistes_by_distance:
            total_distance = piste_stat['piste__length'] * piste_stat['ride_count']
            pistes_with_total_distance.append({
                'piste__id': piste_stat['piste__id'],
                'piste__name': piste_stat['piste__name'],
                'piste__length': piste_stat['piste__length'],
                'ride_count': piste_stat['ride_count'],
                'total_distance': total_distance
            })

        # Sort by total distance and get the top one
        if pistes_with_total_distance:
            pistes_with_total_distance.sort(key=lambda x: x['total_distance'], reverse=True)
            top_piste = pistes_with_total_distance[0]

            try:
                piste = Piste.objects.select_related('way').get(id=top_piste['piste__id'])
                most_distance_piste_ever = {
                    'piste': piste,
                    'piste__name': top_piste['piste__name'],
                    'ride_count': top_piste['ride_count'],
                    'total_distance': top_piste['total_distance']
                }
            except Piste.DoesNotExist:
                logger.warning(f"Piste {top_piste['piste__id']} not found")

    # Most piste rides in one day
    # Calculate piste rides per activity
    activities_with_piste_rides = []
    for activity in activities.filter(ski_area__isnull=False)[:50]:  # Limit for performance
        piste_rides_count = PisteRide.objects.filter(
            lap__activity=activity
        ).count()
        if piste_rides_count > 0:
            activities_with_piste_rides.append((activity, piste_rides_count))

    # Sort by piste rides count
    activities_with_piste_rides.sort(key=lambda x: x[1], reverse=True)
    best_single_day_activity = activities_with_piste_rides[0] if activities_with_piste_rides else None

    # Most unique pistes in one day
    activities_with_unique_pistes = []
    for activity in activities.filter(ski_area__isnull=False)[:50]:  # Limit for performance
        unique_pistes_count = PisteRide.objects.filter(
            lap__activity=activity
        ).values('piste').distinct().count()
        if unique_pistes_count > 0:
            activities_with_unique_pistes.append((activity, unique_pistes_count))

    # Sort by unique pistes count
    activities_with_unique_pistes.sort(key=lambda x: x[1], reverse=True)
    most_unique_pistes_day = activities_with_unique_pistes[0] if activities_with_unique_pistes else None

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
    else:
        overall_completeness = {
            'total_ski_areas': 0,
            'overall_percentage': 0
        }

    # Top ski areas by piste completeness
    ski_area_completeness = []

    # Get all visited ski areas (filtered by season)
    all_visited_ski_areas = SkiArea.objects.filter(
        activity__user=request.user
    ).filter(activity__in=activities).distinct()

    # Get total count for "View All" button logic
    total_ski_areas_count = all_visited_ski_areas.count()

    # Limit to first 10 for performance in main display
    visited_ski_areas = all_visited_ski_areas[:10]

    for ski_area in visited_ski_areas:
        completeness = calculate_ski_area_piste_completeness(request.user, ski_area, season=season)

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

    # Piste difficulty statistics
    piste_difficulty_stats = PisteRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).values(
        'piste__piste_difficulty'
    ).annotate(
        count=Count('id')
    ).order_by('-count')

    # Season-specific statistics
    total_piste_rides = PisteRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).count()

    # Calculate unique pistes separately
    unique_pistes = PisteRide.objects.filter(
        lap__activity__user=request.user
    ).filter(filter_query).values('piste').distinct().count()

    # Calculate total distance skied
    # Only sum length for pistes that have length (non-area pistes)
    # We rely on the fact that area pistes should have length=None
    total_distance_skied = PisteRide.objects.filter(
        lap__activity__user=request.user,
        piste__length__isnull=False
    ).filter(filter_query).aggregate(
        total=Sum('piste__length')
    )['total'] or 0

    season_stats = {
        'total_activities': activities.count(),
        'total_piste_rides': total_piste_rides,
        'unique_pistes': unique_pistes,
        'total_distance_skied': round(total_distance_skied, 1)
    }

    # Piste difficulty breakdown for donut chart
    difficulty_colors = {
        'novice': '#4caf50',
        'easy': '#2196f3',
        'intermediate': '#f44336',
        'advanced': '#212121',
        'expert': '#ff5722',
        'freeride': '#ff9800',
    }
    piste_difficulty_chart = json.dumps([
        {
            'difficulty': (row['piste__piste_difficulty'] or 'unknown').title(),
            'count': row['count'],
            'color': difficulty_colors.get(row['piste__piste_difficulty'] or '', '#9e9e9e'),
        }
        for row in piste_difficulty_stats
    ])

    context = {
        'recent_rides': recent_rides,
        'most_ridden_piste_ever': most_ridden_piste_ever,
        'most_distance_piste_ever': most_distance_piste_ever,
        'best_single_day_activity': best_single_day_activity,
        'most_unique_pistes_day': most_unique_pistes_day,
        'overall_completeness': overall_completeness,
        'ski_area_completeness': ski_area_completeness[:10],
        'total_ski_areas': total_ski_areas_count,
        'piste_difficulty_stats': piste_difficulty_stats,
        'piste_difficulty_chart': piste_difficulty_chart,
        'season_stats': season_stats,
        'seasons': seasons,
        'selected_season': season,
    }

    return render(request, 'activities/piste_insights.html', context)


@login_required
@premium_season_required
def ski_area_piste_completeness_detail(request, ski_area_id, season=None):
    """Show detailed piste completeness view for a specific ski area."""
    ski_area = SkiArea.objects.get(id=ski_area_id)

    # Get season filter
    filter_query = get_filter_query(request, season)
    seasons = filter_seasons_for_user(get_seasons(user=request.user), request.user)

    # Get all available pistes in this ski area
    available_pistes = get_available_pistes_in_ski_area(ski_area, user=request.user)

    # Calculate completeness for this ski area (with season filtering)
    completeness = calculate_ski_area_piste_completeness(request.user, ski_area, season=season)

    # Get pistes the user has ridden with additional stats
    user_piste_rides = PisteRide.objects.filter(
        lap__activity__user=request.user,
        lap__activity__ski_area=ski_area,
        piste__in=available_pistes
    )

    if season:
        user_piste_rides = user_piste_rides.filter(filter_query)

    # Get ridden pistes with stats
    ridden_piste_stats = user_piste_rides.values(
        'piste__id',
        'piste__name',
        'piste__piste_difficulty',
        'piste__length',
    ).annotate(
        total_rides=Count('id'),
        first_ride=Min('timestamp'),
        last_ride=Max('timestamp'),
        unique_days=Count('lap__activity__timestamp__date', distinct=True)
    ).order_by('-total_rides', 'piste__name')

    # Get piste objects for ridden pistes
    ridden_piste_ids = [stat['piste__id'] for stat in ridden_piste_stats]
    ridden_pistes = available_pistes.filter(id__in=ridden_piste_ids)

    # Create lookup for stats
    stats_lookup = {stat['piste__id']: stat for stat in ridden_piste_stats}

    # Combine piste objects with stats
    ridden_pistes_with_stats = []
    for piste in ridden_pistes:
        piste_data = stats_lookup[piste.id]
        ridden_pistes_with_stats.append({
            'piste': piste,
            'total_rides': piste_data['total_rides'],
            'first_ride': piste_data['first_ride'],
            'last_ride': piste_data['last_ride'],
            'unique_days': piste_data['unique_days'],
            'length': piste.length,
            'total_distance': piste.length * piste_data['total_rides'] if piste.length else None
        })

    # Sort by total rides descending
    ridden_pistes_with_stats.sort(key=lambda x: x['total_distance'], reverse=True)

    # Get not ridden pistes
    not_ridden_pistes = available_pistes.exclude(id__in=ridden_piste_ids).order_by('-length', 'name')

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
        'ridden_pistes_with_stats': ridden_pistes_with_stats,
        'not_ridden_pistes': not_ridden_pistes,
        'recent_activities': recent_activities,
        'total_visits': total_visits,
        'seasons': seasons,
        'selected_season': season,
    }

    return render(request, 'activities/ski_area_piste_completeness_detail.html', context)


@login_required
@premium_season_required
def ski_area_piste_completeness_all(request, season=None):
    """Show piste completeness for all ski areas."""

    logger.debug(f"Calculating piste completeness for all ski areas for user {request.user.id} and season {season}")

    # Get season filter
    seasons = filter_seasons_for_user(get_seasons(user=request.user), request.user)

    # Get all ski areas by piste completeness
    ski_area_completeness = []
    visited_ski_areas = SkiArea.objects.filter(
        activity__user=request.user
    ).distinct()

    for ski_area in visited_ski_areas:
        completeness = calculate_ski_area_piste_completeness(request.user, ski_area, season=season)

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
        'page_title': 'All Ski Area Piste Completeness'
    }

    return render(request, 'activities/ski_area_piste_completeness_all.html', context)


@login_required
def reload_ski_area_piste_completeness(request, ski_area_id):
    """API endpoint to reload/refresh ski area piste completeness data."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'AJAX requests only'}, status=400)

    try:
        ski_area = SkiArea.objects.get(id=ski_area_id)

        # Get season from request if provided
        season = request.GET.get('season')

        # Clear cache for this ski area piste completeness
        cache_key = f"piste_completeness_{request.user.id}_{ski_area.id}"
        if season:
            cache_key += f"_{season}"
        cache.delete(cache_key)

        # Recalculate with force_calc=True
        completeness = calculate_ski_area_piste_completeness(request.user, ski_area, force_calc=True, season=season)

        return JsonResponse({
            'success': True,
            'message': 'Piste completeness data refreshed successfully',
            'completeness': completeness
        })

    except SkiArea.DoesNotExist:
        return JsonResponse({'error': 'Ski area not found'}, status=404)
    except Exception as e:
        logger.error(f"Error reloading piste completeness for ski area {ski_area_id}: {e}")
        return JsonResponse({'error': 'Error refreshing piste completeness data'}, status=500)
