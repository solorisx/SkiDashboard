import logging
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.serializers import serialize
from django.contrib.gis.geos import LineString, Point
from django.db.models import F
from django.db.models.functions import Round
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from activities.models import LiftRide
from cost.forms import CostForm
from osm.models import Aerialway, Piste, PisteSegment
from osm.osm_util import get_aerialways_with_distance

from ..models import Activity
from ..utils.queries import get_user_activities_base_query

logger = logging.getLogger(__name__)


def get_unique_lift_rides(activity):
    """Get count of unique lift rides for an activity."""
    return activity.laps.lift_rides.values('aerialway').distinct().count()


@login_required
def activity_list(request):
    """Show all activities with pagination and cost management."""
    logger.debug(f"Request method: {request.method}")
    
    if request.method == 'POST':
        if 'dflt_cst' in request.POST:
            pk = request.POST.get('dflt_cst')
            logger.debug(f"Activity ID: {pk}")
            activity = Activity.objects.get(id=pk, user=request.user)
            cost = activity.ski_area_main.daypass_price
            if cost:
                activity.cost = cost
                activity.save()
            else:
                logger.debug(f"No default cost set for ski area {activity.ski_area_main.name}.")
                activity.cost = 75
                activity.save()
                
        elif 'set_cst' in request.POST:
            pk = request.POST.get('set_cst')
            activity = Activity.objects.get(pk=pk, user=request.user)
            form = CostForm(request.POST, instance=activity)
            if form.is_valid():
                form.save()
            else:
                logger.debug(f"Form is invalid.")
                return HttpResponse("Invalid form.")
        return redirect('activity_list')

    activities = get_user_activities_base_query(request.user).order_by("-timestamp")
    
    activities = activities.annotate(
        total_distance_km=Round(F("total_distance")/1000, 2),
    )

    paginator = Paginator(activities, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'activities/activity_list.html', {'page_obj': page_obj})


@login_required
def activity_detail(request, activity_id):
    """Show details of a single activity, including laps and lift rides."""
    try:
        activity = (
            Activity.objects.annotate(
                total_distance_km=Round(F("total_distance") / 1000.0, 2)
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

    return render(
        request,
        "activities/activity_detail.html",
        {
            "activity": activity,
            "laps": laps,
            "lift_rides": lift_rides,
            "badges": activity.badges.all(),
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