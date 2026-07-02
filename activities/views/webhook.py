import json
import logging
import os
import requests

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

from ..models import Activity
from ..tasks import sync_strava_activity_task

logger = logging.getLogger(__name__)


@csrf_exempt
def strava_webhook(request):
    """Handle Strava webhook events."""
    logger.info(f"Strava webhook received: {request}")
    
    if request.method == "GET":
        return _handle_webhook_verification(request)
    elif request.method == "POST":
        return _handle_webhook_payload(request)


def _handle_webhook_verification(request):
    """Handle webhook verification challenge from Strava."""
    mode = request.GET.get("hub.mode")
    challenge = request.GET.get("hub.challenge")
    verify_token = request.GET.get("hub.verify_token")

    if mode == "subscribe" and verify_token == os.getenv("STRAVA_VERIFY_TOKEN"):
        return JsonResponse({"hub.challenge": challenge})
    else:
        logger.warning("Strava webhook verification failed.")
        # Avoid logging the verify_token (a shared secret).
        logger.debug(f"Mode: {mode}")
        return HttpResponse("Verification failed.", status=403)


def _handle_webhook_payload(request):
    """Handle webhook payload from Strava."""
    try:
        payload = json.loads(request.body)
        logger.debug(f"Received Strava webhook: {payload}")
        
        if payload.get("object_type") != "activity":
            return HttpResponse("OK")
            
        activity_id = payload.get("object_id")
        aspect_type = payload.get("aspect_type")
        
        try:
            user = get_user_model().objects.get(
                socialaccount__uid=payload.get("owner_id"), 
                socialaccount__provider="strava"
            )
        except get_user_model().DoesNotExist:
            logger.error(f"No user found for Strava ID {payload.get('owner_id')}", exc_info=True, stack_info=True)
            return HttpResponse("OK")
        
        if aspect_type == "create":
            return _handle_activity_create(user, activity_id, payload.get("owner_id"))
        elif aspect_type == "delete":
            return _handle_activity_delete(user, activity_id)
            
        return HttpResponse("OK")
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload", exc_info=True, stack_info=True)
        return HttpResponse("Bad Request", status=400)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True, stack_info=True)
        return HttpResponse("Internal Server Error", status=500)


def _handle_activity_create(user, activity_id, user_id):
    """Handle creation of new activity."""
    if Activity.objects.filter(user=user, strava_id=activity_id).exists():
        logger.info(f"Activity {activity_id} for user {user.username} ({user_id}) already exists; skipping.")
        return HttpResponse("OK")
        
    sync_strava_activity_task.delay(user.id, activity_id)
    logger.info(f"Enqueued sync for new activity for user {user.username} ({user_id})")
    return HttpResponse("OK")


def _handle_activity_delete(user, activity_id):
    """Handle deletion of activity.

    Scope the lookup to the user resolved from the webhook's ``owner_id`` so a
    forged payload cannot delete another user's activity (Strava does not sign
    webhook POSTs, so ``owner_id``/``object_id`` are attacker-controllable).
    """
    deleted, _ = Activity.objects.filter(user=user, strava_id=activity_id).delete()
    if deleted:
        logger.info(f"Deleted activity {activity_id} for user {user.username} as per Strava webhook.")
    else:
        logger.info(f"Activity {activity_id} not found for user {user.username}; nothing to delete.")

    return HttpResponse("OK")


@staff_member_required
def subscribe_strava_webhook(request):
    """Subscribe to Strava webhooks."""
    logger.info("Subscribing to Strava webhooks...")
    
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    verify_token = os.getenv("STRAVA_VERIFY_TOKEN")
    callback_url = os.getenv("STRAVA_WEBHOOK_CALLBACK_URL")
    
    # Do not log the verify_token or client_id — they are secrets used to
    # authenticate the webhook handshake.
    logger.info(f"Callback URL: {callback_url}")

    if not all([client_id, client_secret, verify_token, callback_url]):
        messages.error(request, "Missing Strava webhook configuration in environment variables.")
        return redirect("admin:index")
        
    response = requests.post(
        "https://www.strava.com/api/v3/push_subscriptions",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "callback_url": callback_url,
            "verify_token": verify_token,
        },
    )
    
    logger.info(f"Strava webhook subscription response: {response.status_code}, {response.text}")
    
    if response.status_code == 201:
        messages.success(request, "Successfully subscribed to Strava webhooks.")
    else:
        messages.error(request, f"Failed to subscribe to Strava webhooks: {response.text}")
        
    return redirect("admin:index")