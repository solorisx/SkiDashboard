from django.shortcuts import render

from django.contrib import admin
from .models import Activity

from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from .activity_parser import sync_strava_activity
from allauth.socialaccount.models import SocialAccount
from .forms import StravaSyncForm
import logging

# def sync_strava(request):
#     if request.method == "POST":
#         form = StravaSyncForm(request.POST)
#         if form.is_valid():
#             account = SocialAccount.objects.select_related('user').get(user=user, provider='strava')
#             if not account:
#                 messages.error(request, f"User {user} does not have a Strava account.")
#                 return redirect("admin:sync-strava")
#             strava_activity_id = form.cleaned_data["strava_activity_id"]
#             user = form.cleaned_data["user"]
#             try:
#                 sync_strava_activity(user, strava_activity_id)
#                 messages.success(request, f"Successfully synced Strava activity {strava_activity_id} for {user}.")
#             except Exception as e:
#                 messages.error(request, f"Error syncing Strava activity: {e}")
#             return redirect("admin:sync-strava")
#     else:
#         form = StravaSyncForm()
#     return render(request, "admin/strava-admin.html", {"form": form})
