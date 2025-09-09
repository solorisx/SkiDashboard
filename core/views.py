from datetime import datetime
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg, Min, Max, F, Sum, Q
from django.db.models.functions import Round
from django.db import models
from django.http import HttpResponse
from activities.models import Activity, LiftRide, Lap
from osm.models import SkiArea, Aerialway


from .core.skiarea_manager import init_networks
from cost.forms import CostForm
from django.db.models import Count, OuterRef, Subquery
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from dal import autocomplete
from activities.views import home_stats, season_stats
import os

from activities.strava_interface import deauthorize_strava

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import View
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from allauth.socialaccount.models import SocialAccount, SocialToken

from .forms import UserDeleteForm

logger = logging.getLogger(__name__)

def landing(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "landing.html")


@login_required
def home(request):
    return home_stats(request)


@staff_member_required
def initialize_ski_area_networks(request):
    init_networks(request)
    return HttpResponse("Ski area networks initialized.")


class UserDeleteView(LoginRequiredMixin, View):
    """
    Deletes the currently signed-in user and all associated data.
    """
    def get(self, request, *args, **kwargs):
        form = UserDeleteForm()
        return render(request, 'account/user_deletion.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = UserDeleteForm(request.POST)
        # Form will be valid if checkbox is checked.
        if form.is_valid():
            user = request.user
            deauthorize_strava(user.id)
            logout(request)
            # Delete user (and any associated ForeignKeys, according to
            # on_delete parameters).
            user.delete()
            messages.success(request, 'Account successfully deleted')
            return redirect(reverse('home'))
        return render(request, 'account/user_deletion.html', {'form': form})

@login_required
def strava_connection_view(request):
    sa = SocialAccount.objects.filter(user=request.user, provider="strava").first()
    return render(request, "account/strava.html", {"strava_account": sa})

@login_required
@require_http_methods(["POST"])
def strava_unlink_view(request):
    sa = SocialAccount.objects.filter(user=request.user, provider="strava").first()
    if not sa:
        messages.info(request, "Your account is not linked to Strava.")
        return redirect("strava-connection")
    try:
        deauthorize_strava(request.user)
    except Exception:
        messages.warning(request, "Could not reach Strava to revoke; unlinking locally.")

    logger.debug("Deleting Strava SocialAccount and SocialToken for user %s", request.user.username)
    SocialToken.objects.filter(account=sa).delete()
    sa.delete()
    messages.success(request, "Strava has been unlinked.")
    return redirect("strava-connection")

def privacy_policy(request):
    return render(request, "base/privacy.html")

def terms_of_service(request):
    return render(request, "base/terms.html")


# API endpoints

@login_required
def season_stats_api(request):
    return season_stats(request)

@require_http_methods(["POST", "PATCH", "DELETE"])
@login_required
def lift_ride_api(request, lift_ride_id=None):
    """ API endpoint to get, delete, or modify a lift ride by ID. """
    if lift_ride_id:
        lift_ride = LiftRide.objects.filter(id=lift_ride_id, lap__activity__user=request.user).first()
        if not lift_ride:
            return JsonResponse({"error": "Lift ride not found or does not belong to user."}, status=404)

    if request.method == "DELETE":
        lift_ride.delete()
        return HttpResponse(status=204)

    elif request.method == "PATCH":
        logger.debug("Received PATCH data: %s", request.body)
        data = json.loads(request.body)
        if data.get("aerialway"):
            aerialway = Aerialway.objects.filter(id=data["aerialway"]).first()
            if not aerialway:
                return JsonResponse({"error": "Aerialway not found."}, status=404)
            lift_ride.aerialway = aerialway
        if data.get("timestamp"):
            activity_date = lift_ride.lap.activity.start_time.date()
            combined_dt = datetime.strptime(f"{activity_date} {data['timestamp']}", "%Y-%m-%d %H:%M")
            lift_ride.timestamp = combined_dt
        if data.get("lap"):
            lift_ride.lap_id = int(data["lap"])
        if data.get("uphill"):
            lift_ride.uphill = (str(data["uphill"]).lower() == "true")
        lift_ride.save()
        return HttpResponse(status=204)
    
    elif request.method == "POST":
        data = json.loads(request.body)
        logger.debug("Received lift ride data: %s", data)
        if data.get("aerialway") and data.get("lap") and data.get("timestamp") and data.get("uphill"):
            aerialway = Aerialway.objects.filter(id=data["aerialway"]).first()
            if not aerialway:
                return JsonResponse({"error": "Aerialway not found."}, status=404)
            lap = Lap.objects.filter(id=data["lap"], activity__user=request.user).first()
            if not lap:
                return JsonResponse({"error": "Lap not found or does not belong to user."}, status=404)
            time_str = data["timestamp"]
            activity_date = lap.activity.start_time.date()
            combined_dt = datetime.strptime(f"{activity_date} {time_str}", "%Y-%m-%d %H:%M")
            uphill = str(data["uphill"]).lower() == "true"
            lift_ride = LiftRide.objects.create(
                aerialway=aerialway,
                timestamp=combined_dt,
                lap=lap,
                uphill=uphill
            )
            lift_ride.save()
            return HttpResponse(status=201)
        
        else:
            return HttpResponse(status=400)
