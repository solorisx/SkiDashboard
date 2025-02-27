from django.contrib import admin
from .models import Node, Way, Station, Aerialway, Piste, SkiArea

# admin.py
from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from .forms import OSMSyncForm, OSMFileSyncForm
from .osm_downloader import load_osm
from .osm_parser import parse_osm_file
import logging

logger = logging.getLogger('core')

User = get_user_model()

class SyncAdmin(admin.ModelAdmin):
    change_list_template = "admin/osm-admin.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("sync-osm/", self.admin_site.admin_view(self.sync_osm), name="sync-osm"),
            path("sync-osm-api/", self.admin_site.admin_view(self.sync_osm_api), name="sync-osm-api"),
            path("sync-osm-file/", self.admin_site.admin_view(self.sync_osm_file), name="sync-osm-file"),
        ]
        return custom_urls + urls

    def sync_osm(self, request):
        form1 = OSMSyncForm()
        form2 = OSMFileSyncForm()
        return render(request, "admin/osm-admin.html", {"form1": form1, "form2": form2})
        

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




admin.site.register(Node, SyncAdmin)


# admin.site.register(Node)
admin.site.register(Way)
admin.site.register(Station)
admin.site.register(Aerialway)
admin.site.register(Piste)
admin.site.register(SkiArea)
