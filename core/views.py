from datetime import datetime
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Avg, Min, Max, F, Sum, Q
from django.db.models.functions import Round
from django.db import models
from django.http import HttpResponse
from activities.models import Activity, LiftRide
from osm.models import SkiArea, Aerialway
from activities.activity_parser import sync_strava_activity, parse_strava_activities
from .core.skiarea_manager import init_networks
from cost.forms import CostForm
from django.db.models import Count, OuterRef, Subquery
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import os

logger = logging.getLogger(__name__)

def landing(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "landing.html")


@login_required
def home(request):
    return render(request, "home.html")

@staff_member_required
def initialize_ski_area_networks(request):
    init_networks(request)
    return HttpResponse("Ski area networks initialized.")

