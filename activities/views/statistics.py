import logging
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Round
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.db import models
from collections import defaultdict

from activities.models import LiftRide
from osm.models import Aerialway, SkiArea

from ..models import Activity
from ..utils.queries import get_filter_query, get_user_activities_base_query
from ..utils.seasons import get_seasons

logger = logging.getLogger(__name__)


@login_required    
def lift_ride_list(request, year=None):
    """Show lift ride statistics by year."""
    rides = LiftRide.objects.filter(lap__activity__user=request.user)
    years = set(rides.dates("lap__activity__timestamp", "year", order="DESC"))
    years = [y.year for y in years]
    years.sort(reverse=True)

    if year:
        rides = rides.filter(lap__activity__timestamp__year=year)
    
    # Get sort parameter
    sort_by = request.GET.get('sort', 'rides')  # 'rides' or 'area'
    
    # Aggregation by aerialway id
    lift_stats = (
        rides.values("aerialway")
        .annotate(total_rides=Count("id"))
    )

    # Prefetch aerialways with their ski areas
    aerialways = (
        Aerialway.objects
        .filter(pk__in=[s["aerialway"] for s in lift_stats])
        .select_related("way")
        .prefetch_related("way__ski_areas")
    )
    aw_map = {aw.pk: aw for aw in aerialways}

    # Enrich lift stats with aerialway information
    for stat in lift_stats:
        aw = aw_map[stat["aerialway"]]
        stat["aerialway_name"] = aw.name
        stat["location_name"] = aw.get_location.name if aw.get_location else None

    if sort_by == 'area':
        # 1) Per-area totals
        area_totals = defaultdict(int)
        for lift in lift_stats:
            area = lift.get("location_name") or ""
            area_totals[area] += lift.get("total_rides", 0)

        # 2) Add area total to each lift
        for lift in lift_stats:
            area = lift.get("location_name") or ""
            lift["total_rides_area"] = area_totals[area]

        # Helper to get a lift's display name for sorting within area
        def lift_name(l):
            return l.get("lift_name") or l.get("name") or ""

        # 3) Sort: by area total (desc), then area name (asc), then lift name (asc)
        lift_stats = sorted(
            lift_stats,
            key=lambda x: (
                -x.get("total_rides_area", 0),
                (x.get("location_name") or ""),
                -(x.get("total_rides") or 0),
            ),
        )

        # 4) Build ski_area_totals (count + total rides)
        #    Using the already computed area_totals for totals, and a count pass.
        area_counts = defaultdict(int)
        for lift in lift_stats:
            area_counts[lift.get("location_name") or ""] += 1

        ski_area_totals = {
            area: {
                "lift_count": area_counts[area],
                "total_rides": total,
            }
            for area, total in area_totals.items()
        }

    else:
        lift_stats = sorted(lift_stats, key=lambda x: -x.get("total_rides", 0))
        ski_area_totals = {}
        
    # Calculate additional statistics
    total_rides = sum(stat["total_rides"] for stat in lift_stats)
    unique_resorts = len(set(stat["location_name"] for stat in lift_stats if stat["location_name"]))
    top_lift = lift_stats[0] if lift_stats else None

    context = {
        'lift_stats': lift_stats,
        'selected_year': year,
        'years': years,
        'sort_by': sort_by,
        'group_by_area': sort_by == 'area',
        'total_rides': total_rides,
        'unique_resorts': unique_resorts,
        'top_lift': top_lift,
        'ski_area_totals': ski_area_totals,
    }

    return render(request, "liftrides/statistics.html", context)


@login_required
def lift_ride_list_season(request, season=None):
    """Show lift ride statistics by season."""
    rides = LiftRide.objects.filter(lap__activity__user=request.user)
    years = set(rides.dates("lap__activity__timestamp", "year", order="DESC"))
    years = [y.year for y in years]
    years.sort(reverse=True)
    logger.debug(f"Years: {years}")

    if years:
        if not rides.filter(lap__activity__timestamp__lte=datetime(years[-1], 6, 30)):
            years.pop(len(years)-1)

    seasons = [f"{y-1}-{y}" for y in years]

    if season:
        try:
            year1, year2 = map(int, season.split("-"))
        except ValueError:
            return HttpResponse("Invalid season format. Use 'YYYY-YYYY'.")
        if year1 >= year2:
            year1, year2 = year2, year1
        start_date = datetime(year1, 7, 1)
        end_date = datetime(year2, 6, 30)
        rides = rides.filter(lap__activity__timestamp__range=(start_date, end_date))
    
    # Get sort parameter
    sort_by = request.GET.get('sort', 'rides')  # 'rides' or 'area'
    
    # Aggregation by aerialway id
    lift_stats = (
        rides.values("aerialway")
        .annotate(total_rides=Count("id"))
    )

    # Prefetch aerialways with their ski areas
    aerialways = (
        Aerialway.objects
        .filter(pk__in=[s["aerialway"] for s in lift_stats])
        .select_related("way")
        .prefetch_related("way__ski_areas")
    )
    aw_map = {aw.pk: aw for aw in aerialways}

    # Enrich lift stats with aerialway information
    for stat in lift_stats:
        aw = aw_map[stat["aerialway"]]
        stat["aerialway_name"] = aw.name
        stat["location_name"] = aw.get_location.name if aw.get_location else None
        stat["usage_percentage"] = 0  # Will be calculated after sorting

    # Apply sorting
    if sort_by == 'area':
        lift_stats = sorted(lift_stats, key=lambda x: (x["location_name"] or "", -x["total_rides"]))
        # Add ski area totals for grouped view
        from itertools import groupby
        ski_area_totals = {}
        for location, group in groupby(lift_stats, key=lambda x: x["location_name"]):
            group_list = list(group)
            ski_area_totals[location] = {
                'lift_count': len(group_list),
                'total_rides': sum(lift['total_rides'] for lift in group_list)
            }
    else:
        lift_stats = sorted(lift_stats, key=lambda x: -x["total_rides"])
        ski_area_totals = {}
    
    # Calculate additional statistics
    total_rides = sum(stat["total_rides"] for stat in lift_stats)
    unique_resorts = len(set(stat["location_name"] for stat in lift_stats if stat["location_name"]))
    top_lift = lift_stats[0] if lift_stats else None
    
    # Calculate usage percentages
    if total_rides > 0:
        for stat in lift_stats:
            stat["usage_percentage"] = round((stat["total_rides"] / total_rides) * 100, 1)

    context = {
        'lift_stats': lift_stats,
        'selected_season': season,
        'seasons': seasons,
        'sort_by': sort_by,
        'group_by_area': sort_by == 'area',
        'total_rides': total_rides,
        'unique_resorts': unique_resorts,
        'top_lift': top_lift,
        'ski_area_totals': ski_area_totals,
    }

    return render(request, "liftrides/statistics_season.html", context)


@login_required
def activity_list_skiarea(request, season=None):
    """Show activity statistics grouped by ski area."""
    filter_query = get_filter_query(request, season)  
    activities = get_user_activities_base_query(request.user).filter(filter_query).order_by("-timestamp")
    seasons = get_seasons(user=request.user)

    # Group activities by ski area and calculate statistics
    ski_areas = activities.values('ski_area__name').annotate(
        num_act=Count('ski_area__name'),
        ski_area_id=F('ski_area__id'),
        sum_descent=Round(Sum('total_descent'),2),
        total_distance_km=Round((Sum('total_distance')/1000),2),
        total_num_laps=Sum('num_laps'),
        total_num_lift_rides=Sum('num_lift_rides'),
    ).order_by('-num_act')

    # Calculate unique lift rides per ski area
    for ski_area in ski_areas:
        ski_area['total_num_dist_rides'] = LiftRide.objects.filter(
            filter_query, lap__activity__user=request.user, lap__activity__ski_area__id=ski_area['ski_area_id']
        ).values('aerialway').distinct().count()

    # Calculate progress (unique rides vs total available rides)
    for ski_area in ski_areas:
        skiarea = SkiArea.objects.get(id=ski_area['ski_area_id'])
        if skiarea.geom:
            aerialways = Aerialway.objects.filter(station_nodes__node__geom__within=skiarea.geom).distinct()
            ski_area['total_num_area_rides'] = aerialways.count()
        else:
            ski_area['total_num_area_rides'] = Aerialway.objects.filter(way__in=skiarea.ways).distinct().count()
        progress = ski_area['total_num_dist_rides'] / ski_area['total_num_area_rides'] * 100 if ski_area['total_num_area_rides'] else 0
        ski_area['progress'] = round(progress, 1)

    # Calculate overall statistics
    total_activities = activities.aggregate(
        total_cost=Sum('cost'),
        total_value=Sum('value'),
        sum_descent=Round(Sum('total_descent'),2),
        total_distance_km=Round(Sum(F("total_distance"))/1000, 2),
        avg_cost=Avg('cost'),
        num_act=Count('id', distinct=True),
        total_num_laps=Sum('num_laps'),
        total_num_lift_rides=Sum('num_lift_rides'),
    )

    # Calculate totals for unique and area rides
    num_unique_rides = 0
    num_area_rides = 0
    for ski_area in ski_areas:
        num_unique_rides += ski_area['total_num_dist_rides']
        num_area_rides += ski_area['total_num_area_rides']
    total_activities['total_num_dist_rides'] = num_unique_rides
    total_activities['total_num_area_rides'] = num_area_rides
    total_activities['progress'] = round(num_unique_rides * 100.0 / num_area_rides, 1) if num_area_rides else 0

    context = {
        'activities': total_activities,
        'ski_areas': ski_areas,
        'seasons': seasons,
    }

    return render(request, "activities/skiarea/skiarea_list.html", context)


@login_required
def activity_list_skiarea_detail(request, skiarea_id, season=None):
    """Show detailed activity statistics for a specific ski area."""
    skiarea = get_object_or_404(SkiArea, id=skiarea_id)
    filter_query = get_filter_query(request, season)
    activities = get_user_activities_base_query(request.user).filter(filter_query, ski_area=skiarea).order_by("-timestamp")
    
    activities = activities.annotate(
        total_distance_km=Round(F("total_distance")/1000, 2),
        num_distinct_lift_rides=Count('laps__lift_rides__id', distinct=True),
    )
    
    # Debug logging for lift rides
    for activity in activities:
        for lap in activity.laps.all():
            for lift_ride in lap.lift_rides.all():
                logger.debug(f"Lift: {lift_ride.aerialway}")
        logger.debug(f"Activity: {activity}, {activity.num_distinct_lift_rides}")

    seasons = get_seasons(request.user)
    
    # Calculate total statistics for the ski area
    total_activities = activities.aggregate(
        sum_descent=Sum('total_descent'),
        total_distance_km=Sum('total_distance')/1000,
        total_num_laps=Count('laps'),
        num_act=Count('id'),
    )
    total_activities['total_num_lift_rides'] = sum(
        lap.lift_rides.count() for activity in activities for lap in activity.laps.all()
    )
    
    # Get all aerialways in the ski area
    if skiarea.geom:
        aerialways = Aerialway.objects.filter(station_nodes__node__geom__within=skiarea.geom).distinct()
    else:
        aerialways = Aerialway.objects.filter(way__in=skiarea.ways).distinct()
    
    # Annotate aerialways with lift ride counts
    lift_rides_count = LiftRide.objects.filter(
        filter_query,
        aerialway=OuterRef("pk"),
    ).values("aerialway").annotate(num_rides=Count("id")).values("num_rides")

    aerialways = aerialways.annotate(
        num_rides=Subquery(lift_rides_count, output_field=models.IntegerField())
    )

    num_area_rides = aerialways.count()
    logger.debug(f"Num area rides: {num_area_rides}")
    
    # Calculate progress for each activity
    if num_area_rides:
        activities = activities.annotate(
            progress=Round(F("num_distinct_lift_rides") * 100.0 / num_area_rides, 1),
        )

    context = {
        'skiarea': skiarea,
        'activities': activities,
        'total_activities': total_activities,
        'aerialways': aerialways,
        'seasons': seasons,
    }

    return render(request, "activities/skiarea/skiarea_detail.html", context)