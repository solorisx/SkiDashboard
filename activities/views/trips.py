import logging

from django.contrib.auth.decorators import login_required
from django.contrib.gis.db.models.functions import AsGeoJSON, Centroid
from django.db.models import F, Q, Exists, OuterRef, Sum, Count
from django.db.models.functions import Round
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from activities.models import Activity, Trip
from activities.trips import cluster_activities_into_trips
from cost.models import SeasonPass
from ..utils.queries import get_user_activities_base_query

logger = logging.getLogger(__name__)


@login_required
def trip_list(request):
    """Show all trips for the current user."""
    trips = (
        Trip.objects.filter(user=request.user)
        .prefetch_related('activities__ski_area')
        .order_by('-start_date')
    )

    # Annotate each trip with aggregate stats
    trips_annotated = Trip.objects.filter(user=request.user).annotate(
        activity_count=Count('activities'),
        total_descent=Sum('activities__total_descent'),
        total_distance=Sum('activities__total_distance'),
        total_lift_rides=Sum('activities__num_lift_rides'),
    ).order_by('-start_date')

    # Build a lookup from fully annotated queryset
    annotated_lookup = {t.id: t for t in trips_annotated}

    # Merge annotations into the prefetch queryset
    trip_list_data = []
    for trip in trips:
        annotated = annotated_lookup.get(trip.id, trip)
        trip.activity_count = annotated.activity_count or 0
        trip.total_descent = annotated.total_descent or 0
        trip.total_distance_km = round((annotated.total_distance or 0) / 1000, 1)
        trip.total_lift_rides = annotated.total_lift_rides or 0

        # Collect unique ski areas
        ski_areas = []
        seen = set()
        for activity in trip.activities.all():
            if activity.ski_area and activity.ski_area.id not in seen:
                seen.add(activity.ski_area.id)
                ski_areas.append(activity.ski_area)
        trip.ski_areas = ski_areas

        trip_list_data.append(trip)

    return render(request, 'trips/trip_list.html', {
        'trips': trip_list_data,
    })


@login_required
def trip_detail(request, trip_id):
    """Show details of a single trip with all its activities."""
    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)

    season_pass_subquery = SeasonPass.objects.filter(
        user=request.user,
        valid_from__lte=OuterRef('timestamp__date'),
        valid_until__gte=OuterRef('timestamp__date'),
    ).filter(
        Q(skiarea=OuterRef('ski_area')) |
        Q(skiarea_network__members__member=OuterRef('ski_area'))
    )

    activities = (
        get_user_activities_base_query(request.user)
        .filter(trip=trip)
        .annotate(
            total_distance_km=Round(F('total_distance') / 1000, 2),
            has_season_pass=Exists(season_pass_subquery),
            geom_geojson=AsGeoJSON('geom'),
            geom_centroid=Centroid('geom'),
        )
        .order_by('timestamp')
    )

    # Aggregate stats for the trip
    stats = activities.aggregate(
        total_descent=Sum('total_descent'),
        total_distance=Sum('total_distance'),
        total_lift_rides=Sum('num_lift_rides'),
        activity_count=Count('id'),
    )

    # Unique ski areas
    ski_areas = []
    seen = set()
    for act in activities:
        if act.ski_area and act.ski_area.id not in seen:
            seen.add(act.ski_area.id)
            ski_areas.append(act.ski_area)

    return render(request, 'trips/trip_detail.html', {
        'trip': trip,
        'activities': activities,
        'ski_areas': ski_areas,
        'total_descent': stats.get('total_descent') or 0,
        'total_distance_km': round((stats.get('total_distance') or 0) / 1000, 1),
        'total_lift_rides': stats.get('total_lift_rides') or 0,
        'activity_count': stats.get('activity_count') or 0,
    })


@login_required
@require_http_methods(['POST'])
def rename_trip(request, trip_id):
    """Rename a trip (JSON API endpoint)."""
    import json

    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)

    try:
        data = json.loads(request.body)
        new_name = data.get('name', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not new_name:
        return JsonResponse({'error': 'Name cannot be empty'}, status=400)

    if len(new_name) > 200:
        return JsonResponse({'error': 'Name is too long (max 200 characters)'}, status=400)

    trip.name = new_name
    trip.name_modified = True
    trip.save(update_fields=['name', 'name_modified', 'modified_on'])

    return JsonResponse({'id': trip.id, 'name': trip.name})


@login_required
@require_http_methods(['POST'])
def recluster_trips(request):
    """Trigger re-clustering of activities into trips for the current user."""
    cluster_activities_into_trips(request.user)
    return JsonResponse({'status': 'ok'})
