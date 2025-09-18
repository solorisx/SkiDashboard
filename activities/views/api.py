import logging
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.db.models.functions import Round
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json

from cost.models import SeasonPass
from osm.models import SkiArea

from ..utils.completeness import calculate_activity_completeness, calculate_batch_activity_completeness
from ..models import Activity
from ..utils.queries import get_user_activities_base_query
from ..utils.seasons import get_season_dates

logger = logging.getLogger(__name__)


@login_required
def season_stats(request):
    """
    Dedicated API endpoint for season stats AJAX calls.
    """
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'AJAX requests only'}, status=400)
    
    # Get season from query parameter
    season_param = request.GET.get('season', 'current')
    current = season_param == 'current'
    
    # Calculate season dates
    season_start, season_end = get_season_dates(current)
    
    logger.debug(f"Season: {season_start} to {season_end}")

    # Get activities for the season
    activities = get_user_activities_base_query(request.user).filter(
        timestamp__gte=season_start, 
        timestamp__lte=season_end
    )
    
    logger.debug(f"Activities count: {activities.count()}")

    # Get most popular ski area
    skiarea = (
        activities.values("ski_area")
        .annotate(count=Count("ski_area"))
        .order_by("-count")
        .first()
    )

    # Calculate total stats
    total_stats = activities.aggregate(
        total_distance_km=Round(Sum(F("total_distance"))/1000, 2),
        total_descent=Sum("total_descent"),
        total_num_laps=Sum("num_laps"),
        total_num_lift_rides=Sum("num_lift_rides"),
        total_num_activities=Count("id"),
    )

    # Handle None values
    for key in total_stats:
        if total_stats[key] is None:
            total_stats[key] = 0

    # Prepare skiarea data
    skiarea_data = None
    if skiarea:
        try:
            ski_area_obj = SkiArea.objects.get(id=skiarea["ski_area"])
            skiarea_data = {
                "id": ski_area_obj.id,
                "name": ski_area_obj.name,
            }
        except SkiArea.DoesNotExist:
            pass
    
    logger.debug(f"Ski area data: {skiarea_data}")

    return JsonResponse({
        "season": f"{season_start.year}-{season_end.year}",
        "skiarea": skiarea_data,
        "count": skiarea["count"] if skiarea else 0,
        "total_stats": total_stats,
        "current_season": current,
    })


def home_stats(request):
    """
    Generate statistics for the home page.
    """
    season_start, season_end = get_season_dates(current=True)
    activities = get_user_activities_base_query(request.user).filter(
        timestamp__gte=season_start, 
        timestamp__lte=season_end
    )
    
    skiarea = (
        activities.values("ski_area")
        .annotate(count=Count("ski_area"))
        .order_by("-count")
        .first()
    )

    logger.debug(f"Ski area: {skiarea}")

    total_stats = activities.aggregate(
        total_distance_km=Round(Sum(F("total_distance"))/1000, 2),
        total_descent=Sum("total_descent"),
        total_num_laps=Sum("num_laps"),
        total_num_lift_rides=Sum("num_lift_rides"),
        total_num_activities=Count("id"),
    )

    # Handle None values
    if not total_stats['total_distance_km']:
        total_stats['total_distance_km'] = 0
    if not total_stats['total_descent']:
        total_stats['total_descent'] = 0
    if not total_stats['total_num_laps']:
        total_stats['total_num_laps'] = 0
    if not total_stats['total_num_lift_rides']:
        total_stats['total_num_lift_rides'] = 0

    # Calculate season pass statistics
    season_passes = SeasonPass.objects.filter(
        user=request.user, 
        valid_from__lte=season_end, 
        valid_until__gte=season_start
    )
    
    for sp in season_passes:
        logger.debug(f"Season pass: {sp}")
        activities_for_pass = sp.get_valid_activities(season_start, season_end)
        logger.debug(f"Activities: {activities_for_pass}")
    
    season_pass_stats = {}
    if season_passes:
        for sp in season_passes:
            activities_for_pass = sp.get_valid_activities(season_start, season_end)
            if activities_for_pass:
                season_pass_stats[sp] = {
                    'name': sp.skiarea.name if sp.skiarea else sp.skiarea_network, 
                    'activities': activities_for_pass.count(), 
                    'total_savings': activities_for_pass.aggregate(total_savings=Sum('value'))['total_savings']
                }
    
    logger.debug(f"Season pass stats: {season_pass_stats}")

    return {
        "season": f"{season_start.year}-{season_end.year}",
        "skiarea": SkiArea.objects.get(id=skiarea["ski_area"]) if skiarea else None,
        "count": skiarea["count"] if skiarea else 0,
        "total_stats": total_stats,
        "season_passes": season_pass_stats,
    }


@login_required
def activity_completeness_api(request, activity_id):
    """API endpoint to get completeness data for a specific activity."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'AJAX requests only'}, status=400)

    try:
        activity = Activity.objects.get(id=activity_id, user=request.user)
        completeness_data = calculate_activity_completeness(activity)
        return JsonResponse(completeness_data)
    except Activity.DoesNotExist:
        return JsonResponse({'error': 'Activity not found'}, status=404)
    except Exception as e:
        logger.error(f"Error calculating completeness for activity {activity_id}: {e}")
        return JsonResponse({'error': 'Error calculating completeness'}, status=500)


@login_required
def activity_completeness_batch_api(request):
    """Batch API endpoint to get completeness data for multiple activities."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'AJAX requests only'}, status=400)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST requests only'}, status=405)

    try:
        import json
        data = json.loads(request.body)
        activity_ids = data.get('activity_ids', [])

        if not activity_ids:
            return JsonResponse({'error': 'No activity IDs provided'}, status=400)

        if len(activity_ids) > 100:  # Reasonable limit
            return JsonResponse({'error': 'Too many activity IDs (max 100)'}, status=400)

        # Get activities for user with related data
        activities = Activity.objects.filter(
            id__in=activity_ids,
            user=request.user
        ).select_related('ski_area').prefetch_related(
            'laps__lift_rides'
        )

        # Calculate completeness for batch of activities efficiently
        results = calculate_batch_activity_completeness(list(activities), request.user)

        return JsonResponse({'results': results})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in batch completeness API: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)