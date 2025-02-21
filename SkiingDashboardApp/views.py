from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from .models import Activity, LiftRide

# Create your views here.

def hello_world(request):
    return HttpResponse("Hello, World!")

def activity_list(request):
    """Show all activities."""
    activities = Activity.objects.filter(user=request.user)
    return render(request, "activities/activity_list.html", {"activities": activities})

def activity_detail(request, activity_id):
    """Show details of a single activity, including laps and lift rides."""
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)
    laps = activity.laps.all()
    lift_rides = LiftRide.objects.filter(lap__activity=activity)

    return render(
        request,
        "activities/activity_detail.html",
        {
            "activity": activity,
            "laps": laps,
            "lift_rides": lift_rides,
        },
    )