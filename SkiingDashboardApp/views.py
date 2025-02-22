from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, Min, Max, F
from django.http import HttpResponse
from .models import Activity, LiftRide
from SkiingDashboard.core.activity_parser import parse_strava_activity, parse_strava_activities

def hello_world(request):
    return HttpResponse("Hello, World!")

def activity_list(request):
    """Show all activities."""
    activities = Activity.objects.filter(user=request.user).order_by("-timestamp")
    return render(request, "activities/activity_list.html", {"activities": activities})

def activity_detail(request, activity_id):
    """Show details of a single activity, including laps and lift rides."""
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)
    laps = activity.laps.all().order_by("lap_index")
    lift_rides = LiftRide.objects.filter(lap__activity=activity).order_by("lap__lap_index")

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
    
def sync_strava(request):
    try:
        parse_strava_activities(user=request.user, update=False)
        return HttpResponse("Strava activities synced.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")
    
def sync_reprocess_all(request):
    try:
        parse_strava_activities(user=request.user, update=True)
        return HttpResponse("Strava activities synced and reprocessed.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")
    
def lift_ride_list(request, year=None):
    """Show all lift rides."""

    years = set(LiftRide.objects.dates("lap__activity__timestamp", "year", order="DESC"))
    years = [y.year for y in years]
    years.sort(reverse=True)
    
    rides = LiftRide.objects.filter(lap__activity__user=request.user)
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
