


from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import admin
from django.core.paginator import Paginator
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import GEOSGeometry, LineString, Point
from allauth.socialaccount.models import SocialAccount
from datetime import datetime
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg, Min, Max, F, Sum, Q
from django.db.models.functions import Round
from django.db import models
from django.http import HttpResponse
from activities.models import Activity, LiftRide
from osm.models import SkiArea, Aerialway, PisteSegment
from cost.forms import CostForm
from django.db.models import Count, OuterRef, Subquery
from django.core.serializers import serialize

from .models import Activity
from .forms import StravaSyncForm
from .activity_parser import sync_strava_activity, parse_strava_activities, parse_strava_activity

logger = logging.getLogger('core')

@staff_member_required
def sync_strava_admin(request):
    if request.method == "POST":
        form = StravaSyncForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data["user"]
            account = SocialAccount.objects.select_related('user').get(user=user, provider='strava')
            if not account:
                messages.error(request, f"User {user} does not have a Strava account.")
                return redirect("sync_strava_admin")
            strava_activity_id = form.cleaned_data["strava_activity_id"]
            user = form.cleaned_data["user"]
            update = form.cleaned_data["update"]
            try:
                sync_strava_activity(user, strava_activity_id, update)
                messages.success(request, f"Successfully synced Strava activity {strava_activity_id} for {user}.")
            except Exception as e:
                messages.error(request, f"Error syncing Strava activity: {e}")
                return redirect("sync_strava_admin")
    else:
        form = StravaSyncForm()
    return render(request, 'admin/strava-admin.html', {"form": form})


@login_required
def sync_strava(request):
    try:
        parse_strava_activities(user=request.user, all=False, update=False)
        return HttpResponse("Strava activities synced.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")


@staff_member_required    
def sync_reprocess_all(request):
    try:
        parse_strava_activities(user=request.user, update=True, all=True)
        return HttpResponse("Strava activities synced and reprocessed.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")
    

@staff_member_required    
def reset_all(request):
    Activity.objects.filter(user=request.user).delete()
    return HttpResponse("All activities deleted.")


def get_seasons(user):
    activities = Activity.objects.filter(user=user)
    years = set(activities.dates("timestamp", "year", order="DESC"))
    years = [y.year for y in years]
    years.sort(reverse=True)
    if years:
        if not activities.filter(timestamp__lte=datetime(years[-1], 6, 30)):
            years.pop(len(years)-1)
    seasons = [f"{y-1}-{y}" for y in years]
    return seasons 


def get_unique_lift_rides(activity):
    return activity.laps.lift_rides.values('aerialway').distinct().count()


def get_filter_query(request, season):
    filter = Q()
    if season:
        try:
            year1, year2 = map(int, season.split("-"))
        except ValueError:
            return HttpResponse("Invalid season format. Use 'YYYY-YYYY'.")
        if year1 >= year2:
            year1, year2 = year2, year1
        start_date = datetime(year1, 7, 1)
        end_date = datetime(year2, 6, 30)
        filter = Q(timestamp__range=(start_date, end_date))  
    return filter


@login_required
def activity_list(request):
    """Show all activities."""

    logger.debug(f"Request method: {request.method}")
    if request.method == 'POST':
        if 'dflt_cst' in request.POST:
            pk = request.POST.get('dflt_cst')
            logger.debug(f"Activity ID: {pk}")
            activity = Activity.objects.get(id=pk)
            logger.debug(f"Activity: {activity}")
            activity = Activity.objects.get(id=pk, user=request.user)
            cost = activity.ski_area_main.daypass_price
            if cost:
                activity.cost = cost
                activity.save()
            else:
                logger.debug(f"No default cost set for ski area {activity.ski_area_main.name}.")
                activity.cost = 75
                activity.save()
        if 'set_cst' in request.POST:
            pk = request.POST.get('set_cst')
            activity = Activity.objects.get(pk=pk, user=request.user)
            form = CostForm(request.POST, instance=activity)
            if form.is_valid():
                form.save()
            else:
                logger.debug(f"Form is invalid.")
                return HttpResponse("Invalid form.")
        return redirect('activity_list')

    activities = Activity.objects.filter(user=request.user).order_by("-timestamp")
    
    activities = ( 
        activities
        .select_related("ski_area")
        .prefetch_related("badges")
        .annotate(
            
            
            total_distance_km=Round(F("total_distance")/1000, 2),
            
        )
    )

    paginator = Paginator(activities, 10)  # Show 10 activities per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'activities/activity_list.html', {'page_obj': page_obj})    

    # return render(request, "activities/activity_list.html", {"activities": activities})


@login_required
def activity_detail(request, activity_id):
    """Show details of a single activity, including laps and lift rides."""
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)
    laps = activity.laps.all().order_by("lap_index")
    lift_rides = LiftRide.objects.filter(lap__activity=activity).order_by("lap__lap_index", "timestamp")

    return render(
        request,
        "activities/activity_detail.html",
        {
            "activity": activity,
            "laps": laps,
            "lift_rides": lift_rides,
            "badges": activity.badges.all(),
        },
    )

@login_required
def reprocess_activity(request, activity_id):
    """Reprocess an activity to update its laps and lift rides."""
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)
    if activity.strava_id:
        parse_strava_activity(user=request.user, activity_id=activity.strava_id, update=True)
        return HttpResponse(f"Activity {activity_id} reprocessed.")
    else:
        return HttpResponse(f"Activity {activity_id} has no Strava ID.")


@staff_member_required
def sync_strava_all(request):
    try:
        parse_strava_activities(user=request.user, all=True, update=False)
        return HttpResponse("Strava activities synced.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")


@login_required
def sync_strava(request):
    try:
        parse_strava_activities(user=request.user, all=False, update=False)
        return HttpResponse("Strava activities synced.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")


@login_required    
def lift_ride_list(request, year=None):
    """Show all lift rides."""

    rides = LiftRide.objects.filter(lap__activity__user=request.user)
    years = set(rides.dates("lap__activity__timestamp", "year", order="DESC"))
    years = [y.year for y in years]
    years.sort(reverse=True)

    if year:
        rides = rides.filter(lap__activity__timestamp__year=year)
    
    lift_stats = rides.values('aerialway__name').annotate(
        total_rides=Count('id'),
    ).order_by('-total_rides')

    context = {
        'lift_stats': lift_stats,
        'selected_year': year,
        'years': years
    }

    return render(request, "liftrides/statistics.html", context)


@login_required
def lift_ride_list_season(request, season=None):
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
    
    lift_stats = rides.values('aerialway__name').annotate(
        total_rides=Count('id'),
    ).order_by('-total_rides')

    context = {
        'lift_stats': lift_stats,
        'selected_season': season,
        'seasons': seasons
    }

    return render(request, "liftrides/statistics_season.html", context)


@login_required
def activity_list_skiarea(request, season=None):

    filter = get_filter_query(request, season)  
    activities = Activity.objects.filter(filter, user=request.user).order_by("-timestamp")
    seasons = get_seasons(user=request.user)

    ski_areas = activities.values('ski_area__name').annotate(
        num_act=Count('ski_area__name'),
        ski_area_id=F('ski_area__id'),
        sum_descent=Round(Sum('total_descent'),2),
        total_distance_km=Round((Sum('total_distance')/1000),2),
        total_num_laps=Sum('num_laps'),
        total_num_lift_rides=Sum('num_lift_rides'),
        # num_unique_liftrides=Count('laps__lift_rides__aerialway', distinct=True)        
    ).order_by('-num_act')

    for ski_area in ski_areas:
        ski_area['total_num_dist_rides'] = LiftRide.objects.filter(
            filter, lap__activity__user=request.user, lap__activity__ski_area__id=ski_area['ski_area_id']
        ).values('aerialway').distinct().count()

    for ski_area in ski_areas:
        skiarea = SkiArea.objects.get(id=ski_area['ski_area_id'])
        if skiarea.geom:
            aerialways = Aerialway.objects.filter(station_nodes__node__geom__within=skiarea.geom).distinct()
            ski_area['total_num_area_rides'] = aerialways.count()
        else:
            ski_area['total_num_area_rides'] = Aerialway.objects.filter(way__in=skiarea.ways).distinct().count()
        progress = ski_area['total_num_dist_rides'] / ski_area['total_num_area_rides'] * 100 if ski_area['total_num_area_rides'] else 0
        ski_area['progress'] = round(progress, 1)


    activities = activities.aggregate(
        total_cost=Sum('cost'),
        total_value=Sum('value'),
        sum_descent=Round(Sum('total_descent'),2),
        total_distance_km=Round(Sum(F("total_distance"))/1000, 2),
        avg_cost=Avg('cost'),
        num_act=Count('id', distinct=True),
        total_num_laps=Sum('num_laps'),
        total_num_lift_rides=Sum('num_lift_rides'),
    )

    num_unique_rides = 0
    num_area_rides = 0
    for ski_area in ski_areas:
        num_unique_rides += ski_area['total_num_dist_rides']
        num_area_rides += ski_area['total_num_area_rides']
    activities['total_num_dist_rides'] = num_unique_rides
    activities['total_num_area_rides'] = num_area_rides
    activities['progress'] = round(num_unique_rides * 100.0 / num_area_rides , 1) if num_area_rides else 0

    context = {
        'activities': activities,
        'ski_areas': ski_areas,
        'seasons': seasons,
    }


    return render(request, "activities/skiarea/skiarea_list.html", context)


@login_required
def activity_list_skiarea_detail(request, skiarea_id, season=None):
    skiarea = get_object_or_404(SkiArea, id=skiarea_id)
    filter = get_filter_query(request, season)
    activities = Activity.objects.filter(filter, user=request.user, ski_area=skiarea).order_by("-timestamp")
    activities = activities.annotate(
        total_distance_km=Round(F("total_distance")/1000, 2),
        num_distinct_lift_rides=Count('laps__lift_rides__id', distinct=True),
    )
    
    for activity in activities:
        for lap in activity.laps.all():
            for lift_ride in lap.lift_rides.all():
                logger.debug(f"Lift: {lift_ride.aerialway}")
            
        logger.debug(f"Activity: {activity}, {activity.num_distinct_lift_rides}")

    seasons = get_seasons(request.user)
    total_activities = activities.aggregate(
        sum_descent=Sum('total_descent'),
        total_distance_km=Sum('total_distance')/1000,
        total_num_laps=Count('laps'),
        num_act=Count('id'),
    )
    total_activities['total_num_lift_rides'] = sum(
        lap.lift_rides.count() for activity in activities for lap in activity.laps.all()
    )
    
    if skiarea.geom:
        aerialways = Aerialway.objects.filter(station_nodes__node__geom__within=skiarea.geom).distinct() # TODO: create geom for way and check if way is within skiarea.geom
    else:
        aerialways = Aerialway.objects.filter(way__in=skiarea.ways).distinct()
    
    # Subquery to count lift rides per Aerialway
    lift_rides_count = LiftRide.objects.filter(
        filter,
        aerialway=OuterRef("pk"),
    ).values("aerialway").annotate(num_rides=Count("id")).values("num_rides")

    # Annotate the aerialways queryset with the lift ride count
    aerialways = aerialways.annotate(
        num_rides=Subquery(lift_rides_count, output_field=models.IntegerField())
    )

    num_area_rides = aerialways.count()
    logger.debug(f"Num area rides: {num_area_rides}")
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


def swap_coords(geom):
    """ Swap lat/lon if needed (for GeoJSON compatibility). """
    if geom.geom_type == "Point":
        return Point(geom.y, geom.x, srid=4326)  # Swap X (lon) and Y (lat)
    elif geom.geom_type == "LineString":
        return LineString([(p[1], p[0]) for p in geom.coords], srid=4326)  # Swap all points
    return geom

def segment_map(request, activity_id):
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

    # Ensure segment geometries are in EPSG:4326 and swap lat/lon
    # for segment in piste_segments:
    #     if segment.geom.srid != 4326:
    #         segment.geom.transform(4326)
    #     segment.geom = swap_coords(segment.geom)

    # Serialize segment geometries
    segments_geojson = serialize("geojson", piste_segments, geometry_field="geom")

    return render(request, "segment_map.html", {
        "activity_id": activity.strava_id,
        "way_geojson": way_geojson,
        "segments_geojson": segments_geojson,
    })


def home_stats(request):
    current_season_start = datetime(datetime.now().year, 7, 1) if datetime.now().month >= 7 else datetime(datetime.now().year-1, 7, 1)
    activities = Activity.objects.filter(user=request.user, timestamp__gte=current_season_start)
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
    )
    return render(request, "home.html", {
        "skiarea": SkiArea.objects.get(id=skiarea["ski_area"]) if skiarea else None,
        "count": skiarea["count"] if skiarea else 0,
        "total_stats": total_stats,
    })


