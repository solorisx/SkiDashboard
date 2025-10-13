from datetime import datetime
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg, Min, Max, F, Sum, Q
from django.db.models.functions import Round
from django.db import models
from django.http import HttpResponse
from activities.models import Activity, LiftRide, Lap
from osm.models import SkiArea, Aerialway, SkiAreaNetwork
from cost.models import SeasonPass


from .core.skiarea_manager import init_networks
from cost.forms import CostForm
from django.db.models import Count, OuterRef, Subquery
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from dal import autocomplete
from activities.views import home_stats, season_stats
from djmoney.models.fields import MoneyField
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
from djmoney.money import Money

from .forms import UserDeleteForm, UserProfileForm
from .models import UserProfile

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
            if SocialAccount.objects.filter(user=user, provider="strava").exists():
                # Try to deauthorize Strava if the user has a connected account
                try:
                    deauthorize_strava(user)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to deauthorize Strava for user {user.username}: {e}")
            logout(request)
            user.delete()
            messages.success(request, 'Account successfully deleted')
            return redirect(reverse('home'))
        return render(request, 'account/user_deletion.html', {'form': form})

@login_required
def strava_connection_view(request):
    sa = SocialAccount.objects.filter(user=request.user, provider="strava").first()

    # Get current scopes from account extra_data if connected
    current_scopes = []
    if sa and sa.extra_data:
        # Strava returns scope in the token response, stored in extra_data
        scope_str = sa.extra_data.get('scope')
        if scope_str:
            current_scopes = scope_str.split(',')

    # Get what scopes will be requested based on user preferences
    from core.strava_adapter import get_dynamic_strava_scope
    requested_scopes = get_dynamic_strava_scope(request)

    context = {
        "strava_account": sa,
        "current_scopes": current_scopes,
        "requested_scopes": requested_scopes,
    }
    return render(request, "account/strava.html", context)

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


@login_required
def profile_management(request):
    """User profile management view."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'POST':
        logger.debug("Received profile update POST data: %s", request.POST)

        # Store original opt_in_strava_write value
        original_strava_write = profile.opt_in_strava_write

        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            updated_profile = form.save()

            # Check if opt_in_strava_write changed
            strava_write_changed = original_strava_write != updated_profile.opt_in_strava_write

            if strava_write_changed:
                # Check if user has Strava connected
                strava_account = SocialAccount.objects.filter(
                    user=request.user,
                    provider="strava"
                ).first()

                if strava_account:
                    # Store that reauth is needed in session
                    request.session['strava_reauth_needed'] = True
                    request.session['strava_reauth_write_scope'] = updated_profile.opt_in_strava_write
                    messages.warning(
                        request,
                        'Strava write access changed. Please reconnect your Strava account to apply the new permissions.'
                    )
                    return redirect('strava-connection')

            messages.success(request, 'Profile settings updated successfully.')
            return redirect('profile_management')
        else:
            logger.warning("UserProfileForm is not valid: %s", form.errors)
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserProfileForm(instance=profile)

    return render(request, 'account/profile.html', {
        'form': form,
        'profile': profile
    })


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
        
class SeasonPassAPI(LoginRequiredMixin, View):
    """
    API endpoint to get, create, update, or delete a season pass.
    """
    def get(self, request, season_pass_id=None):
        raise NotImplementedError("GET method not implemented in SeasonPassAPI.")

    def post(self, request):
        data = json.loads(request.body)
        logger.debug("Received season pass data: %s", data)
        if (data.get("skiarea") or data.get("skiarea_network")) and data.get("valid_from") and data.get("valid_until") and data.get("price_0") and data.get("price_1"):
            if data.get("skiarea") and data.get("skiarea_network"):
                return JsonResponse({"error": "A season pass must be for either a ski area or a ski area network, not both."}, status=400)
            if data.get("skiarea_network"):
                skiarea_network = SkiAreaNetwork.objects.filter(id=data["skiarea_network"]).first()
            if data.get("skiarea"):
                skiarea = SkiArea.objects.filter(id=data["skiarea"]).first()
            valid_from = datetime.strptime(data["valid_from"], "%Y-%m-%d")
            valid_until = datetime.strptime(data["valid_until"], "%Y-%m-%d")
            amount   = data.get('price_0')  # string like "549.00"
            currency = data.get('price_1')  # "CHF"
            price = Money(amount, currency) if amount and currency else None
            season_pass = SeasonPass.objects.create(
                user=request.user,
                skiarea=skiarea if data.get("skiarea") else None,
                skiarea_network=skiarea_network if data.get("skiarea_network") else None,
                valid_from=valid_from,
                valid_until=valid_until,
                price=price
            )
            season_pass.save()
            return HttpResponse(status=201)

        else:
            return HttpResponse(status=400)

    def patch(self, request, season_pass_id):
        data = json.loads(request.body)
        logger.debug("Received season pass update data: %s", data)
        season_pass = SeasonPass.objects.filter(id=season_pass_id, user=request.user).first()
        if not season_pass:
            return JsonResponse({"error": "Season pass not found or does not belong to user."}, status=404)
        if data.get("skiarea"):
            skiarea = SkiArea.objects.filter(id=data["skiarea"]).first()
            if not skiarea:
                return JsonResponse({"error": "Ski area not found."}, status=404)
            season_pass.skiarea = skiarea
            season_pass.skiarea_network = None
        if data.get("skiarea_network"):
            skiarea_network = SkiAreaNetwork.objects.filter(id=data["skiarea_network"]).first()
            if not skiarea_network:
                return JsonResponse({"error": "Ski area network not found."}, status=404)
            season_pass.skiarea_network = skiarea_network
            season_pass.skiarea = None
        if data.get("valid_from"):
            season_pass.valid_from = datetime.strptime(data["valid_from"], "%Y-%m-%d")
        if data.get("valid_until"):
            season_pass.valid_until = datetime.strptime(data["valid_until"], "%Y-%m-%d")
        amount   = data.get('price_0')  # string like "549.00"
        currency = data.get('price_1')  # "CHF"
        price = Money(amount, currency) if amount and currency else None
        if price:
            season_pass.price = price
        season_pass.save()
        return HttpResponse(status=204)
    
    def delete(self, request, season_pass_id):
        season_pass = SeasonPass.objects.filter(id=season_pass_id, user=request.user).first()
        if not season_pass:
            return JsonResponse({"error": "Season pass not found or does not belong to user."}, status=404)
        season_pass.delete()
        return HttpResponse(status=204)
