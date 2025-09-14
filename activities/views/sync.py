import logging
import time
import os
from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..batch import parse_strava_activities, parse_strava_activity
from ..forms import GlobalSyncForm, PerUserSyncForm, StravaSyncForm
from ..models import Activity
from ..tasks import (
    scheduled_strava_sync,
    sync_strava_activity_task,
    sync_user_activities_task as sync_user_new_activities_task,
)

logger = logging.getLogger(__name__)

# Track activities currently being reprocessed with timestamps to avoid duplicates
_reprocessing_activities = {}


def _clean_completed_reprocessing_tasks():
    """Clean up completed reprocessing tasks from tracking dict."""
    current_time = time.time()
    timeout = os.getenv("REPROCESSING_TIMEOUT", 300)  # Default to 5 minutes
    # Remove entries older than timeout
    expired_keys = [key for key, timestamp in _reprocessing_activities.items()
                   if current_time - timestamp > timeout]
    for key in expired_keys:
        _reprocessing_activities.pop(key, None)

    if expired_keys:
        logger.info(f"Cleaned up {len(expired_keys)} expired reprocessing entries")


@staff_member_required
def sync_strava_admin(request):
    """Admin interface for syncing Strava activities."""
    activity_form = StravaSyncForm()
    peruser_form = PerUserSyncForm()
    global_form = GlobalSyncForm()

    if request.method == "POST":
        # Single-activity manual sync
        if "action_single_activity" in request.POST:
            activity_form = StravaSyncForm(request.POST)
            if activity_form.is_valid():
                user = activity_form.cleaned_data["user"]
                if not SocialAccount.objects.filter(user=user, provider="strava").exists():
                    messages.error(request, f"User {user} does not have a Strava account.")
                    return redirect("sync_strava_admin")

                strava_activity_id = activity_form.cleaned_data["strava_activity_id"]
                update = activity_form.cleaned_data["update"]
                try:
                    sync_strava_activity_task.delay(user, strava_activity_id, update)
                    messages.success(
                        request,
                        f"Started sync for Strava activity {strava_activity_id} (user: {user})."
                    )
                except Exception as e:
                    messages.error(request, f"Error syncing Strava activity: {e}")
                return redirect("sync_strava_admin")

        # Per-user sweep of new activities (background)
        elif "action_per_user" in request.POST:
            peruser_form = PerUserSyncForm(request.POST)
            if peruser_form.is_valid():
                user = peruser_form.cleaned_data["user"]
                if not SocialAccount.objects.filter(user=user, provider="strava").exists():
                    messages.error(request, f"User {user} does not have a Strava account.")
                    return redirect("sync_strava_admin")

                all_flag = peruser_form.cleaned_data["all"]
                update_flag = peruser_form.cleaned_data["update"]

                sync_user_new_activities_task.delay(user.id, all=all_flag, update=update_flag)
                msg = f"Started sync for {'ALL' if all_flag else 'NEW'} activities (user: {user})"
                if update_flag:
                    msg += ", UPDATING existing activities."
                messages.success(request, msg)
                return redirect("sync_strava_admin")

        # Global sweep for all Strava users (background)
        elif "action_global" in request.POST:
            global_form = GlobalSyncForm(request.POST)
            if global_form.is_valid():
                scheduled_strava_sync.delay(True)
                messages.info(request, "Triggered background sync for all Strava-connected users.")
                return redirect("sync_strava_admin")

    context = {
        "activity_form": activity_form,
        "peruser_form": peruser_form,
        "global_form": global_form,
    }
    return render(request, "admin/strava-admin.html", context)


@login_required
def sync_strava(request):
    """Sync Strava activities for the current user."""
    try:
        parse_strava_activities(user=request.user, all=False, update=False)
        return HttpResponse("Strava activities sync started.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")


@staff_member_required    
def sync_reprocess_all(request):
    """Reprocess all Strava activities for the current user."""
    try:
        parse_strava_activities(user=request.user, update=True, all=True)
        return HttpResponse("Strava activities sync and reprocessing started")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")
    

@staff_member_required    
def reset_all(request):
    """Delete all activities for the current user."""
    Activity.objects.filter(user=request.user).delete()
    return HttpResponse("All activities deleted.")


@staff_member_required
def sync_strava_all(request):
    """Sync all Strava activities for the current user."""
    try:
        parse_strava_activities(user=request.user, all=True, update=False)
        return HttpResponse("Strava activities synced.")
    except Exception as e:
        return HttpResponse(f"Error syncing Strava activities: {e}")


@login_required
def reprocess_activity(request, activity_id, background=True):
    """Reprocess an activity to update its laps and lift rides."""
    # Clean up expired entries first
    _clean_completed_reprocessing_tasks()

    activity = get_object_or_404(Activity, id=activity_id, user=request.user)

    if not activity.strava_id:
        messages.error(request, f"Activity '{activity.name}' has no Strava ID and cannot be reprocessed.")
        return redirect("activity_detail", activity_id=activity_id)

    # Check if activity is already being processed
    activity_key = f"{request.user.id}_{activity.strava_id}"
    if activity_key in _reprocessing_activities:
        messages.info(request, f"Activity '{activity.name}' is already queued for reprocessing.")
        return redirect("activity_detail", activity_id=activity_id)

    try:
        # Add to reprocessing dict with timestamp to prevent duplicates
        _reprocessing_activities[activity_key] = time.time()

        # Queue the reprocessing task
        parse_strava_activity(user=request.user, activity_id=activity.strava_id, update=True, background=background)

        messages.success(request, f"Activity '{activity.name}' has been queued for reprocessing. This may take a few minutes.")
        logger.info(f"Queued activity {activity_id} (Strava ID: {activity.strava_id}) for reprocessing by user {request.user.username}")

    except Exception as e:
        # Remove from dict if queuing failed
        _reprocessing_activities.pop(activity_key, None)
        messages.error(request, f"Failed to queue activity '{activity.name}' for reprocessing: {e}")
        logger.error(f"Failed to queue activity {activity_id} for reprocessing: {e}")

    return redirect("activity_detail", activity_id=activity_id)