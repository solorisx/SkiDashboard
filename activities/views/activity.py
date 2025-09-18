import logging
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_http_methods
from django.views import View
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.core.serializers import serialize
from django.contrib.gis.geos import LineString, Point
from django.db.models import F, Q, Exists, OuterRef, Case, When, IntegerField
from django.db.models.functions import Round
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from itertools import groupby
from operator import attrgetter

from activities.models import LiftRide, Badge
from cost.forms import CostForm
from cost.models import SeasonPass
from osm.models import Aerialway, Piste, PisteSegment, SkiArea
from osm.osm_util import get_aerialways_with_distance

from ..models import Activity
from ..utils.queries import get_user_activities_base_query
from ..utils.seasons import get_seasons, parse_season_string

logger = logging.getLogger(__name__)


def get_unique_lift_rides(activity):
    """Get count of unique lift rides for an activity."""
    return activity.laps.lift_rides.values('aerialway').distinct().count()


@login_required
def activity_list(request):
    """Show all activities with pagination, cost management, filtering and grouping."""
    logger.debug(f"Request method: {request.method}")

    # Check for delete success message
    if request.GET.get('deleted') == '1':
        from django.contrib import messages
        messages.success(request, 'Activity deleted successfully!')

    # Get filter parameters
    ski_area_filter = request.GET.get('ski_area')
    season_filter = request.GET.get('season')
    group_by_ski_area = request.GET.get('group_by') == 'ski_area'

    activities = get_user_activities_base_query(request.user).order_by("-timestamp")

    # Apply ski area filter if specified
    if ski_area_filter:
        try:
            ski_area_id = int(ski_area_filter)
            activities = activities.filter(ski_area_id=ski_area_id)
        except (ValueError, TypeError):
            # Invalid ski_area parameter, ignore it
            pass

    # Apply season filter if specified
    if season_filter:
        try:
            start_date, end_date = parse_season_string(season_filter, request.user)
            if start_date and end_date:
                activities = activities.filter(timestamp__range=[start_date, end_date])
        except (ValueError, TypeError):
            # Invalid season parameter, ignore it
            pass

    # Create a subquery to check for valid season passes
    season_pass_subquery = SeasonPass.objects.filter(
        user=request.user,
        valid_from__lte=OuterRef('timestamp__date'),
        valid_until__gte=OuterRef('timestamp__date')
    ).filter(
        Q(skiarea=OuterRef('ski_area')) |  # Direct ski area match
        Q(skiarea_network__members__member=OuterRef('ski_area'))  # Ski area network match through members
    )

    activities = activities.annotate(
        total_distance_km=Round(F("total_distance")/1000, 2),
        has_season_pass=Exists(season_pass_subquery),
    ).prefetch_related('ski_area')

    # Get available ski areas and seasons for the filter dropdowns
    available_ski_areas = SkiArea.objects.filter(
        activity__user=request.user
    ).distinct().order_by('name')

    available_seasons = get_seasons(request.user)

    # Pre-calculate selected ski area to avoid O(n) template lookups
    selected_ski_area = None
    if ski_area_filter:
        try:
            ski_area_id = int(ski_area_filter)
            selected_ski_area = SkiArea.objects.get(id=ski_area_id)
        except (ValueError, TypeError, SkiArea.DoesNotExist):
            pass


    # Handle grouping by ski area
    if group_by_ski_area:
        # Get all activities ordered by ski area, then by timestamp
        all_activities_query = activities.order_by('ski_area__name', '-timestamp')
        total_count = all_activities_query.count()

        # Group all activities first to avoid splitting groups across pages
        all_activities = list(all_activities_query)
        all_grouped_activities = []
        for ski_area, group in groupby(all_activities, key=attrgetter('ski_area')):
            activities_list = list(group)
            all_grouped_activities.append({
                'ski_area': ski_area,
                'activities': activities_list,
                'count': len(activities_list)
            })

        # paginate by complete groups
        groups_per_page = 5  # Show 5 complete ski area groups per page
        group_paginator = Paginator(all_grouped_activities, groups_per_page)
        page_number = request.GET.get('page', 1)
        page_obj = group_paginator.get_page(page_number)

        grouped_activities = page_obj.object_list

        context = {
            'grouped_activities': grouped_activities,
            'is_grouped': True,
            'available_ski_areas': available_ski_areas,
            'available_seasons': available_seasons,
            'current_ski_area_filter': ski_area_filter,
            'current_season_filter': season_filter,
            'selected_ski_area': selected_ski_area,
            'total_activities': total_count,
            'page_obj': page_obj,  # Include pagination info for grouped mode
        }
    else:
        # Regular pagination
        paginator = Paginator(activities, 12)  # Show 12 activities per page (works as 1×12, 2×6, 3×4 rows)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'is_grouped': False,
            'available_ski_areas': available_ski_areas,
            'available_seasons': available_seasons,
            'current_ski_area_filter': ski_area_filter,
            'current_season_filter': season_filter,
            'selected_ski_area': selected_ski_area,
        }

    return render(request, 'activities/activity_list.html', context)


@login_required
def activity_detail(request, activity_id):
    """Show details of a single activity, including laps and lift rides."""
    try:
        # Create a subquery to check for valid season passes
        season_pass_subquery = SeasonPass.objects.filter(
            user=request.user,
            valid_from__lte=OuterRef('timestamp__date'),
            valid_until__gte=OuterRef('timestamp__date')
        ).filter(
            Q(skiarea=OuterRef('ski_area')) |  # Direct ski area match
            Q(skiarea_network__members__member=OuterRef('ski_area'))  # Ski area network match through members
        )
        
        activity = (
            Activity.objects.annotate(
                total_distance_km=Round(F("total_distance") / 1000.0, 2),
                has_season_pass=Exists(season_pass_subquery),
            )
            .get(id=activity_id, user=request.user)
        )
    except Activity.DoesNotExist:
        raise Http404("Activity not found")
        
    laps = activity.laps.all().order_by("lap_index")
    lift_rides = LiftRide.objects.filter(lap__activity=activity).order_by("lap__lap_index", "timestamp")
    aerialways = (
        Aerialway.objects
        .filter(liftride__lap__activity=activity)
        .distinct()
    )

    aerialways_dropdown = get_aerialways_with_distance(
        lat=activity.start_position.y,
        lon=activity.start_position.x,
        distance_km=20
    )
    badges = sorted(
        activity.badges.all(),
        key=lambda x: (-x.badge.rarity_order, x.badge.name)
    )

    return render(
        request,
        "activities/activity_detail.html",
        {
            "activity": activity,
            "laps": laps,
            "lift_rides": lift_rides,
            "badges": badges,
            "aerialways": aerialways,
            "aerialways_dropdown": aerialways_dropdown,
        },
    )


@login_required
def activity_detail_strava(request, strava_id):
    """Show details of a single activity from Strava ID."""
    activity = get_object_or_404(Activity, strava_id=strava_id, user=request.user)
    return redirect("activity_detail", activity_id=activity.id)


def swap_coords(geom):
    """Swap lat/lon if needed (for GeoJSON compatibility)."""
    if geom.geom_type == "Point":
        return Point(geom.y, geom.x, srid=4326)
    elif geom.geom_type == "LineString":
        return LineString([(p[1], p[0]) for p in geom.coords], srid=4326)
    return geom


def segment_map(request, activity_id):
    """Display segment map for an activity."""
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)

    # Ensure activity geometry is in EPSG:4326
    if activity.geom.srid != 4326:
        activity.geom.transform(4326)

    # Serialize activity geometry
    way_geojson = serialize("geojson", [activity], geometry_field="geom")

    # Get actual piste segment geometries
    piste_segments = PisteSegment.objects.filter(
        id__in=activity.piste_segments.values_list("piste_segment", flat=True)
    )

    skiarea = activity.ski_area
    pistes = Piste.objects.filter(geom__coveredby=skiarea.geom)

    # Serialize segment geometries
    segments_geojson = serialize("geojson", piste_segments, geometry_field="geom")
    piste_geojson = serialize("geojson", pistes, geometry_field="geom")

    return render(request, "segment_map.html", {
        "activity_id": activity.strava_id,
        "way_geojson": way_geojson,
        "segments_geojson": segments_geojson,
        "piste_geojson": piste_geojson,
    })

class ActivityAPI(LoginRequiredMixin, View):
    """API endpoint to delete activity."""

    def delete(self, request, activity_id):
        """Handle DELETE requests to delete an activity."""
        activity = get_object_or_404(Activity, id=activity_id, user=request.user)
        activity_name = activity.name
        skiarea_id = activity.ski_area.id if activity.ski_area else None
        activity.delete()
        from activities.tasks import recalculate_completeness_task
        recalculate_completeness_task.delay(user_id=request.user.id, skiarea_id=skiarea_id)
        logging.getLogger(__name__).info(f"Activity '{activity_name}' (ID: {activity_id}) deleted by user {request.user}")
        return JsonResponse({
            "success": True,
            "message": f"Activity '{activity_name}' deleted successfully"
        }, status=204)