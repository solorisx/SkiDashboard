from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from .models import Activity, LiftRide
from SkiingDashboard.core.activity_parser import parse_strava_activity

# Create your views here.

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