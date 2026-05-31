import json
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.db.models.functions import Round, TruncWeek, TruncMonth
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from cost.models import SeasonPass
from osm.models import SkiArea

from ..utils.completeness import (
    calculate_activity_completeness,
    calculate_batch_activity_completeness,
    calculate_activity_piste_completeness,
    calculate_batch_activity_piste_completeness
)
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
        .annotate(count=Count("id", distinct=True))
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
    """Generate statistics for the home page including YoY comparison and chart data."""
    from datetime import timedelta

    season_start, season_end = get_season_dates(current=True)
    prev_start, prev_end = get_season_dates(current=False)

    activities = get_user_activities_base_query(request.user).filter(
        timestamp__gte=season_start,
        timestamp__lte=season_end
    )
    prev_activities = get_user_activities_base_query(request.user).filter(
        timestamp__gte=prev_start,
        timestamp__lte=prev_end
    )

    skiarea = (
        activities.values("ski_area")
        .annotate(count=Count("id", distinct=True))
        .order_by("-count")
        .first()
    )

    total_stats = activities.aggregate(
        total_distance_km=Round(Sum(F("total_distance"))/1000, 2),
        total_descent=Sum("total_descent"),
        total_num_laps=Sum("num_laps"),
        total_num_lift_rides=Sum("num_lift_rides"),
        total_num_activities=Count("id"),
    )
    for key in total_stats:
        if total_stats[key] is None:
            total_stats[key] = 0

    # Prior season totals for YoY deltas
    prev_stats = prev_activities.aggregate(
        total_distance_km=Round(Sum(F("total_distance"))/1000, 2),
        total_descent=Sum("total_descent"),
        total_num_lift_rides=Sum("num_lift_rides"),
        total_num_activities=Count("id"),
    )
    for key in prev_stats:
        if prev_stats[key] is None:
            prev_stats[key] = 0

    # Weekly descent for line chart (current + prior season)
    def weekly_descent_series(qs, start):
        rows = (
            qs.annotate(week=TruncWeek('timestamp'))
            .values('week')
            .annotate(descent=Sum('total_descent'))
            .order_by('week')
        )
        result = []
        for row in rows:
            offset_days = (row['week'].date() - start.date()).days
            result.append({'offset': offset_days, 'descent': round(row['descent'] or 0)})
        return result

    weekly_current = weekly_descent_series(activities, season_start)
    weekly_prior = weekly_descent_series(prev_activities, prev_start)

    # Descent by ski area (top 5 + Other) for donut chart
    area_breakdown_qs = (
        activities.exclude(ski_area__isnull=True)
        .values('ski_area__name')
        .annotate(descent=Sum('total_descent'))
        .order_by('-descent')[:6]
    )
    area_breakdown = [
        {'name': row['ski_area__name'], 'descent': round(row['descent'] or 0)}
        for row in area_breakdown_qs
    ]

    # Season pass statistics
    season_passes = SeasonPass.objects.filter(
        user=request.user,
        valid_from__lte=season_end,
        valid_until__gte=season_start
    )
    season_pass_stats = {}
    for sp in season_passes:
        activities_for_pass = sp.get_valid_activities(season_start, season_end)
        if activities_for_pass:
            act_count = activities_for_pass.count()
            # Summer activities covered by this pass offset the winter cost/day.
            summer_value = sp.total_summer_value
            summer_value_amount = float(summer_value.amount) if summer_value is not None else 0.0
            cost_per_day = None
            if act_count > 0:
                try:
                    net_amount = float(sp.price.amount) - summer_value_amount
                    cost_per_day = {
                        'amount': round(net_amount / act_count, 2),
                        'currency': str(sp.price.currency),
                    }
                except Exception:
                    pass
            season_pass_stats[sp] = {
                'name': sp.skiarea.name if sp.skiarea else str(sp.skiarea_network),
                'activities': act_count,
                'summer_value': summer_value_amount,
                'cost_per_day': cost_per_day,
            }

    # Unique ski areas this season and prior
    unique_areas = activities.exclude(ski_area__isnull=True).values('ski_area').distinct().count()
    prev_unique_areas = prev_activities.exclude(ski_area__isnull=True).values('ski_area').distinct().count()

    # Average cost per ski day across active season passes
    avg_cost_per_day = None
    if season_pass_stats:
        total_amount = 0.0
        total_acts = 0
        currency = None
        for sp, sp_data in season_pass_stats.items():
            if sp_data['activities'] > 0:
                # Net of summer value, consistent with per-pass winter cost/day.
                total_amount += float(sp.price.amount) - sp_data.get('summer_value', 0.0)
                currency = str(sp.price.currency)
                total_acts += sp_data['activities']
        if total_acts > 0:
            avg_cost_per_day = {
                'amount': round(total_amount / total_acts, 2),
                'currency': currency,
            }

    def fmt_delta(val, prev, decimals=0):
        d = round(val - prev, decimals)
        return f"+{d}" if d > 0 else str(d)

    deltas = {
        'descent': fmt_delta(total_stats['total_descent'], prev_stats['total_descent']),
        'distance_km': fmt_delta(total_stats['total_distance_km'], prev_stats['total_distance_km'], 1),
        'lift_rides': fmt_delta(total_stats['total_num_lift_rides'], prev_stats['total_num_lift_rides']),
        'days': fmt_delta(total_stats['total_num_activities'], prev_stats['total_num_activities']),
        'areas': fmt_delta(unique_areas, prev_unique_areas),
    }

    return {
        "season": f"{season_start.year}-{season_end.year}",
        "prev_season": f"{prev_start.year}-{prev_end.year}",
        "skiarea": SkiArea.objects.get(id=skiarea["ski_area"]) if skiarea else None,
        "count": skiarea["count"] if skiarea else 0,
        "total_stats": total_stats,
        "prev_stats": prev_stats,
        "deltas": deltas,
        "unique_areas": unique_areas,
        "prev_unique_areas": prev_unique_areas,
        "weekly_current": weekly_current,
        "weekly_prior": weekly_prior,
        "area_breakdown": area_breakdown,
        "season_passes": season_pass_stats,
        "avg_cost_per_day": avg_cost_per_day,
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


@login_required
def activity_piste_completeness_api(request, activity_id):
    """API endpoint to get piste completeness data for a specific activity."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'AJAX requests only'}, status=400)

    try:
        activity = Activity.objects.get(id=activity_id, user=request.user)

        # Check if activity has a ski area
        if not activity.ski_area:
            return JsonResponse({
                'distance_skied_today': 0,
                'total_distance_available': 0,
                'daily_completion_percentage': 0,
                'new_pistes_discovered': 0,
                'new_distance_discovered': 0
            })

        completeness_data = calculate_activity_piste_completeness(activity)
        return JsonResponse(completeness_data)
    except Activity.DoesNotExist:
        return JsonResponse({'error': 'Activity not found'}, status=404)
    except Exception as e:
        logger.error(f"Error calculating piste completeness for activity {activity_id}: {e}")
        return JsonResponse({'error': 'Error calculating piste completeness'}, status=500)


@login_required
@require_http_methods(["POST"])
def activity_piste_completeness_batch_api(request):
    """Batch API endpoint to get piste completeness data for multiple activities."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'AJAX requests only'}, status=400)

    try:
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
            'laps__pisteride_set'
        )

        # Calculate piste completeness for batch of activities efficiently
        results = calculate_batch_activity_piste_completeness(list(activities), request.user)

        return JsonResponse({'results': results})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in batch piste completeness API: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)


@login_required
@require_http_methods(["POST"])
def update_strava_description_api(request, activity_id):
    """API endpoint to update the Strava description for an activity."""
    try:
        # Get the activity
        activity = Activity.objects.select_related('user').get(id=activity_id, user=request.user)

        # Check if user has opted in to Strava write
        try:
            user_profile = request.user.userprofile
            if not user_profile.opt_in_strava_write:
                return JsonResponse({
                    'error': 'You must opt in to Strava write access in settings to update descriptions'
                }, status=403)
        except Exception:
            return JsonResponse({
                'error': 'User profile not found'
            }, status=500)

        # Check if activity has been manually modified
        if not activity.manually_modified:
            return JsonResponse({
                'error': 'Activity must be manually modified (add/edit lift rides) before updating Strava description'
            }, status=400)

        # Check if activity has a Strava ID
        if not activity.strava_id:
            return JsonResponse({
                'error': 'Activity does not have a Strava ID'
            }, status=400)

        # Import and use the activity parser to update description
        from ..activity_parser import ActivityParser
        from ..strava_interface import StravaWritePermissionError
        parser = ActivityParser()

        try:
            success = parser.update_strava_description(activity)
        except StravaWritePermissionError:
            return JsonResponse({
                'error': (
                    'Strava write permission is missing. '
                    'Your profile has been reset to read-only. '
                    'Please reconnect Strava with write access to use this feature.'
                )
            }, status=403)

        if success:
            activity.strava_description_updated = True
            activity.save(update_fields=['strava_description_updated'])
            return JsonResponse({
                'success': True,
                'message': 'Strava description updated successfully'
            })
        else:
            return JsonResponse({
                'error': 'Failed to update Strava description. Check logs for details.'
            }, status=500)

    except Activity.DoesNotExist:
        return JsonResponse({'error': 'Activity not found'}, status=404)
    except Exception as e:
        logger.error(f"Error updating Strava description for activity {activity_id}: {e}", exc_info=True)
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)