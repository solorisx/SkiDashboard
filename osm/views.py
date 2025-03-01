from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import OSMSyncForm, OSMFileSyncForm
from .osm_downloader import load_osm
from .osm_parser import parse_osm_file
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
import logging


logger = logging.getLogger(__name__)


@staff_member_required
def sync_osm(request):
    form1 = OSMSyncForm()
    form2 = OSMFileSyncForm()
    return render(request, "admin/osm-admin.html", {"form1": form1, "form2": form2})
    

@staff_member_required
def sync_osm_api(self, request):
    if request.method == "POST":
        form = OSMSyncForm(request.POST)
        if form.is_valid():
            osm_id = form.cleaned_data["osm_id"]
            osm_type = form.cleaned_data["osm_type"]
            try:
                # TODO: Implement OSM API sync
                raise NotImplementedError("OSM API sync not implemented.")
                messages.success(request, f"Successfully loaded OSM data for {osm_type} {osm_id}.")
            except Exception as e:
                messages.error(request, f"Error loading OSM data: {e}")
            return redirect("admin:sync-osm")
    raise ValueError("Invalid request method or invalid form")


@staff_member_required
def sync_osm_file(self, request):
    if request.method == "POST":
        try:
            form = OSMFileSyncForm(request.POST)
            if form.is_valid():
                sync_ways = form.cleaned_data["sync_ways"]
                sync_relations = form.cleaned_data["sync_relations"]
                sync_nodes = form.cleaned_data["sync_nodes"]
                sync_areas = form.cleaned_data["sync_areas"]
                logger.debug(f"Syncing OSM data: ways={sync_ways}, relations={sync_relations}, nodes={sync_nodes}, areas={sync_areas}")
                load_osm()
                logger.debug("Loaded OSM data")
                parse_osm_file("planet_pistes-osmium.osm", [sync_nodes, sync_ways, sync_relations, sync_areas])
                messages.success(request, f"Successfully loaded OSM data from file.")
        except Exception as e:
            messages.error(request, f"Error loading OSM data: {e}")
            return redirect("admin:sync-osm")
    raise ValueError("Invalid request method or invalid form")     
