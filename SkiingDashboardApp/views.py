from datetime import datetime
import logging
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, Min, Max, F
from django.db.models.functions import Round
from django.http import HttpResponse
from .models import Activity, LiftRide
from SkiingDashboard.core.activity_parser import parse_strava_activity, parse_strava_activities
from SkiingDashboard.core.skiarea_manager import init_networks

logger = logging.getLogger('SkiingDashboard')

def hello_world(request):
    return HttpResponse("Hello, World!")

def home(request):
    return render(request, "home.html")

def initialize_ski_area_networks(request):
    init_networks(request)
    return HttpResponse("Ski area networks initialized.")


def activity_list(request):
    """Show all activities."""
    activities = Activity.objects.filter(user=request.user).order_by("-timestamp")

    activities = ( 
        activities
        .select_related("ski_area", "ski_area_boundary")
        .prefetch_related("ski_area_main")
        .annotate(
            num_laps=Count("laps"),
            num_lift_rides=Count("laps__lift_rides"),
            total_distance_km=Round(F("total_distance")/1000, 2),
        )
    )

    return render(request, "activities/activity_list.html", {"activities": activities})

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
        },
    )

def reprocess_activity(request, activity_id):
    """Reprocess an activity to update its laps and lift rides."""
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)
    if activity.strava_id:
        parse_strava_activity(user=request.user, activity_id=activity.strava_id, update=True)
        return HttpResponse(f"Activity {activity_id} reprocessed.")
    else:
        return HttpResponse(f"Activity {activity_id} has no Strava ID.")


def sync_strava_all(request):
    try:
        parse_strava_activities(user=request.user, all=True, update=False)
        return HttpResponse("Strava activities synced.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")


def sync_strava(request):
    try:
        parse_strava_activities(user=request.user, all=False, update=False)
        return HttpResponse("Strava activities synced.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")
    
def sync_reprocess_all(request):
    try:
        parse_strava_activities(user=request.user, update=True)
        return HttpResponse("Strava activities synced and reprocessed.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")
    
def reset_all(request):
    Activity.objects.filter(user=request.user).delete()
    return HttpResponse("All activities deleted.")
    
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
    logger.debug(f"Seasons: {seasons}")
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
