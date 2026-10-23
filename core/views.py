from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
from django.shortcuts import render, redirect
from django.http import HttpResponse
from activities.models import LiftRide, Lap, PisteRide
from osm.models import SkiArea, Aerialway, SkiAreaNetwork
from cost.models import SeasonPass


from .core.skiarea_manager import init_networks
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from activities.views import home_stats, season_stats

from activities.strava_interface import deauthorize_strava

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth import logout
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
        return render(request, "account/user_deletion.html", {"form": form})

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
            messages.success(request, "Account successfully deleted")
            return redirect(reverse("home"))
        return render(request, "account/user_deletion.html", {"form": form})


@login_required
def strava_connection_view(request):
    sa = SocialAccount.objects.filter(user=request.user, provider="strava").first()

    # Get current scopes from account extra_data if connected
    current_scopes = []
    if sa and sa.extra_data:
        # Strava returns scope in the token response, stored in extra_data
        scope_str = sa.extra_data.get("scope")
        if scope_str:
            current_scopes = scope_str.split(",")

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

    # Check if this is first-time profile setup
    is_first_time = not profile.profile_confirmed

    if request.method == "POST":
        logger.debug("Received profile update POST data: %s", request.POST)

        # Store original opt_in_strava_write value
        original_strava_write = profile.opt_in_strava_write

        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            updated_profile = form.save()

            # Mark profile as confirmed on first save
            if is_first_time:
                updated_profile.profile_confirmed = True
                updated_profile.save()
                messages.success(request, "Welcome! Your profile has been set up successfully.")
            else:
                messages.success(request, "Profile settings updated successfully.")

            # Check if opt_in_strava_write changed
            strava_write_changed = original_strava_write != updated_profile.opt_in_strava_write

            if strava_write_changed:
                # Check if user has Strava connected
                strava_account = SocialAccount.objects.filter(user=request.user, provider="strava").first()

                if strava_account:
                    # Store that reauth is needed in session
                    request.session["strava_reauth_needed"] = True
                    request.session["strava_reauth_write_scope"] = updated_profile.opt_in_strava_write
                    messages.warning(
                        request,
                        "Strava write access changed. Please reconnect your Strava account to apply the new permissions.",
                    )
                    return redirect("strava-connection")

            # Redirect to home after successful save
            return redirect("home")
        else:
            logger.warning("UserProfileForm is not valid: %s", form.errors)
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=profile)

    # Check if user has Strava connected
    has_strava = SocialAccount.objects.filter(user=request.user, provider="strava").exists()

    return render(
        request,
        "account/profile.html",
        {
            "form": form,
            "profile": profile,
            "is_first_time": is_first_time,
            "has_strava": has_strava,
        },
    )


# API endpoints


@login_required
def season_stats_api(request):
    return season_stats(request)


@require_http_methods(["POST"])
@login_required
def toggle_dark_mode(request):
    """Toggle dark mode preference for the user."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    profile.dark_mode = not profile.dark_mode
    profile.save(update_fields=["dark_mode"])
    return JsonResponse({"dark_mode": profile.dark_mode})


@require_http_methods(["POST", "PATCH", "DELETE"])
@login_required
def lift_ride_api(request, lift_ride_id=None):
    """API endpoint to get, delete, or modify a lift ride by ID."""
    if lift_ride_id:
        lift_ride = LiftRide.objects.filter(id=lift_ride_id, lap__activity__user=request.user).first()
        if not lift_ride:
            return JsonResponse({"error": "Lift ride not found or does not belong to user."}, status=404)

    if request.method == "DELETE":
        # Mark activity as manually modified
        activity = lift_ride.lap.activity
        activity.manually_modified = True
        activity.save(update_fields=["manually_modified"])
        lift_ride.delete()
        activity.set_num_lift_rides()
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
            activity = lift_ride.lap.activity
            activity_date = activity.start_time.date()
            time_str = data["timestamp"]

            # Create naive datetime from the date and time
            naive_dt = datetime.strptime(f"{activity_date} {time_str}", "%Y-%m-%d %H:%M")

            # Convert to timezone-aware datetime in activity's local timezone, then to UTC
            if activity.timezone:
                import pytz

                try:
                    local_tz = pytz.timezone(activity.timezone)
                    # Localize to activity's timezone
                    local_dt = local_tz.localize(naive_dt)
                    # Convert to UTC
                    lift_ride.timestamp = local_dt.astimezone(pytz.UTC)
                except Exception as e:
                    logger.error(f"Error converting timestamp to timezone: {e}")
                    # Fallback to UTC if timezone conversion fails
                    from django.utils import timezone as django_tz

                    lift_ride.timestamp = django_tz.make_aware(naive_dt, pytz.UTC)
            else:
                # No timezone info, assume UTC
                from django.utils import timezone as django_tz

                lift_ride.timestamp = django_tz.make_aware(naive_dt, pytz.UTC)
        if data.get("lap"):
            lift_ride.lap_id = int(data["lap"])
        if data.get("uphill"):
            lift_ride.uphill = str(data["uphill"]).lower() == "true"
        lift_ride.save()
        # Mark activity as manually modified
        activity = lift_ride.lap.activity
        activity.manually_modified = True
        activity.save(update_fields=["manually_modified"])
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

            activity = lap.activity
            time_str = data["timestamp"]
            activity_date = activity.start_time.date()

            # Create naive datetime from the date and time
            naive_dt = datetime.strptime(f"{activity_date} {time_str}", "%Y-%m-%d %H:%M")

            # Convert to timezone-aware datetime in activity's local timezone, then to UTC
            if activity.timezone:
                import pytz

                try:
                    local_tz = pytz.timezone(activity.timezone)
                    # Localize to activity's timezone
                    local_dt = local_tz.localize(naive_dt)
                    # Convert to UTC for storage
                    utc_dt = local_dt.astimezone(pytz.UTC)
                except Exception as e:
                    logger.error(f"Error converting timestamp to timezone: {e}")
                    # Fallback to UTC if timezone conversion fails
                    from django.utils import timezone as django_tz

                    utc_dt = django_tz.make_aware(naive_dt, pytz.UTC)
            else:
                # No timezone info, assume UTC
                from django.utils import timezone as django_tz

                utc_dt = django_tz.make_aware(naive_dt, pytz.UTC)

            uphill = str(data["uphill"]).lower() == "true"
            lift_ride = LiftRide.objects.create(aerialway=aerialway, timestamp=utc_dt, lap=lap, uphill=uphill)
            lift_ride.save()
            # Mark activity as manually modified
            activity.manually_modified = True
            activity.save(update_fields=["manually_modified"])
            activity.set_num_lift_rides()
            return HttpResponse(status=201)

        else:
            return HttpResponse(status=400)


@require_http_methods(["DELETE"])
@login_required
def piste_ride_api(request, piste_ride_id):
    """API endpoint to delete a piste ride by ID."""
    piste_ride = PisteRide.objects.filter(id=piste_ride_id, lap__activity__user=request.user).first()
    if not piste_ride:
        return JsonResponse({"error": "Piste ride not found or does not belong to user."}, status=404)

    if request.method == "DELETE":
        # Mark activity as manually modified
        activity = piste_ride.lap.activity
        activity.manually_modified = True
        activity.save(update_fields=["manually_modified"])
        piste_ride.delete()
        return HttpResponse(status=204)


class SeasonPassAPI(LoginRequiredMixin, View):
    """
    API endpoint to get, create, update, or delete a season pass.
    Requires an active Premium subscription.
    """

    def _check_premium(self, request):
        try:
            if not request.user.userprofile.is_premium_active():
                return JsonResponse({"error": "Season pass tracking requires a Premium membership."}, status=403)
        except Exception:
            return JsonResponse({"error": "Season pass tracking requires a Premium membership."}, status=403)
        return None

    def get(self, request, season_pass_id=None):
        raise NotImplementedError("GET method not implemented in SeasonPassAPI.")

    def post(self, request):
        err = self._check_premium(request)
        if err:
            return err
        data = json.loads(request.body)
        logger.debug("Received season pass data: %s", data)
        if (
            (data.get("skiarea") or data.get("skiarea_network"))
            and data.get("valid_from")
            and data.get("valid_until")
            and data.get("price_0")
            and data.get("price_1")
        ):
            if data.get("skiarea") and data.get("skiarea_network"):
                return JsonResponse(
                    {"error": "A season pass must be for either a ski area or a ski area network, not both."},
                    status=400,
                )
            if data.get("skiarea_network"):
                skiarea_network = SkiAreaNetwork.objects.filter(id=data["skiarea_network"]).first()
            if data.get("skiarea"):
                skiarea = SkiArea.objects.filter(id=data["skiarea"]).first()
            valid_from = datetime.strptime(data["valid_from"], "%Y-%m-%d")
            valid_until = datetime.strptime(data["valid_until"], "%Y-%m-%d")
            amount = data.get("price_0")  # string like "549.00"
            currency = data.get("price_1")  # "CHF"
            price = Money(amount, currency) if amount and currency else None
            season_pass = SeasonPass.objects.create(
                user=request.user,
                skiarea=skiarea if data.get("skiarea") else None,
                skiarea_network=skiarea_network if data.get("skiarea_network") else None,
                valid_from=valid_from,
                valid_until=valid_until,
                price=price,
            )
            season_pass.save()
            return HttpResponse(status=201)

        else:
            return HttpResponse(status=400)

    def patch(self, request, season_pass_id):
        err = self._check_premium(request)
        if err:
            return err
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
        amount = data.get("price_0")  # string like "549.00"
        currency = data.get("price_1")  # "CHF"
        price = Money(amount, currency) if amount and currency else None
        if price:
            season_pass.price = price
        season_pass.save()
        return HttpResponse(status=204)

    def delete(self, request, season_pass_id):
        err = self._check_premium(request)
        if err:
            return err
        season_pass = SeasonPass.objects.filter(id=season_pass_id, user=request.user).first()
        if not season_pass:
            return JsonResponse({"error": "Season pass not found or does not belong to user."}, status=404)
        season_pass.delete()
        return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Premium / Paywall views
# ---------------------------------------------------------------------------


@login_required
def premium_info(request):
    """Public-facing premium info page."""
    from core.models import PremiumConfig

    profile = request.user.userprofile
    config = PremiumConfig.get_config()
    monthly = config.monthly_price_usd
    yearly = config.yearly_price_usd
    if monthly > 0:
        savings_pct = round((1 - yearly / (monthly * 12)) * 100)
    else:
        savings_pct = 0
    context = {
        "is_premium": profile.is_premium_active(),
        "premium_plan": profile.premium_plan,
        "premium_expires_at": profile.premium_expires_at,
        "premium_payment_source": profile.premium_payment_source,
        "monthly_price_usd": monthly,
        "yearly_price_usd": yearly,
        "yearly_savings_pct": max(savings_pct, 0),
    }
    return render(request, "premium/premium_info.html", context)


@csrf_exempt
def buymeacoffee_webhook(request):
    """Handle BuyMeACoffee payment webhooks to grant premium."""
    from django.conf import settings as django_settings
    from django.contrib.auth.models import User
    from core.premium import grant_premium

    if request.method != "POST":
        return HttpResponse(status=405)

    secret = getattr(django_settings, "BUYMEACOFFEE_WEBHOOK_SECRET", "")
    if not secret:
        # Without a secret anyone could POST a fake payment and grant themselves premium.
        logger.error("BuyMeACoffee webhook rejected: BUYMEACOFFEE_WEBHOOK_SECRET is not configured")
        return HttpResponse(status=403)
    sig = request.headers.get("X-Signature-SHA256", "")
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        logger.warning("BuyMeACoffee webhook signature mismatch")
        return HttpResponse(status=403)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(status=400)

    email = payload.get("supporter_email") or payload.get("payer_email", "")
    try:
        amount = float(payload.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0

    if not email:
        return HttpResponse("OK")

    from core.models import PremiumConfig

    config = PremiumConfig.get_config()
    yearly_threshold = float(config.yearly_threshold_usd)
    monthly_threshold = float(config.monthly_threshold_usd)

    if amount >= yearly_threshold:
        plan = "yearly"
    elif amount >= monthly_threshold:
        plan = "monthly"
    else:
        logger.info(f"BMC webhook: amount {amount} below monthly threshold {monthly_threshold} for {email}")
        return HttpResponse("OK")

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        logger.info(f"BMC webhook: no user found for email {email}")
        return HttpResponse("OK")

    grant_premium(user, source="buymeacoffee", plan=plan)
    return HttpResponse("OK")


@staff_member_required
def membership_admin(request):
    """Admin view: membership stats, grant/revoke controls, and pricing config."""
    from decimal import Decimal, InvalidOperation
    from django.contrib.auth.models import User
    from django.utils import timezone
    from core.premium import grant_premium, revoke_premium
    from core.models import PremiumConfig

    now = timezone.now()
    soon = now + timedelta(days=30)
    ago = now - timedelta(days=30)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "update_config":
            config = PremiumConfig.get_config()
            try:
                config.monthly_price_usd = Decimal(request.POST["monthly_price_usd"])
                config.yearly_price_usd = Decimal(request.POST["yearly_price_usd"])
                config.monthly_threshold_usd = Decimal(request.POST["monthly_threshold_usd"])
                config.yearly_threshold_usd = Decimal(request.POST["yearly_threshold_usd"])
                config.save()
                messages.success(request, "Pricing configuration updated.")
            except (KeyError, InvalidOperation) as e:
                messages.error(request, f"Invalid pricing values: {e}")
            return redirect("membership_admin")

        user_id = request.POST.get("user_id")
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            messages.error(request, "User not found.")
            return redirect("membership_admin")

        if action == "grant":
            plan = request.POST.get("plan", "yearly")
            grant_premium(target, source="manual", plan=plan, granted_by=request.user)
            plan_label = "monthly (30 days)" if plan == "monthly" else "yearly (365 days)"
            messages.success(request, f"Premium granted to {target.email} — {plan_label}.")
        elif action == "revoke":
            revoke_premium(target)
            messages.success(request, f"Premium revoked for {target.email}.")
        else:
            messages.error(request, "Unknown action.")
        return redirect("membership_admin")

    all_users = User.objects.select_related("userprofile").order_by("email")

    total_users = all_users.count()
    active_premium = UserProfile.objects.filter(is_premium=True, premium_expires_at__gt=now).count()
    expiring_soon = (
        UserProfile.objects.filter(is_premium=True, premium_expires_at__range=(now, soon))
        .select_related("user")
        .order_by("premium_expires_at")
    )
    recently_expired = (
        UserProfile.objects.filter(is_premium=True, premium_expires_at__range=(ago, now))
        .select_related("user")
        .order_by("-premium_expires_at")
    )
    premium_users = (
        UserProfile.objects.filter(is_premium=True)
        .select_related("user", "premium_granted_by")
        .order_by("premium_expires_at")
    )

    context = {
        "total_users": total_users,
        "active_premium": active_premium,
        "expiring_soon": expiring_soon,
        "recently_expired": recently_expired,
        "premium_users": premium_users,
        "all_users": all_users,
        "premium_config": PremiumConfig.get_config(),
    }
    return render(request, "admin/membership.html", context)
