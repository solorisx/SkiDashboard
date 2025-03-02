from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import OSMSyncForm, OSMFileSyncForm, SkiAreaNetworkForm
from .osm_downloader import load_osm
from .osm_parser import parse_osm_file
from .models import SkiArea, SkiAreaNetwork, SkiAreaNetworkMember
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import logging
from dal import autocomplete


logger = logging.getLogger(__name__)


@staff_member_required
def sync_osm(request):
    form1 = OSMSyncForm()
    form2 = OSMFileSyncForm()
    form3 = SkiAreaNetworkForm()
    return render(request, "admin/osm-admin.html", {"form1": form1, "form2": form2, "form3": form3})
    

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
def sync_osm_file(request):
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
            return redirect("sync_osm")
    raise ValueError("Invalid request method or invalid form")


@staff_member_required
def assign_skiarea_network(request):
    if request.method == "POST":
        form = SkiAreaNetworkForm(request.POST)
        if form.is_valid():
            skiarea = form.cleaned_data["skiarea"]
            skiarea_network = form.cleaned_data["skiarea_network"]
            _, created = SkiAreaNetworkMember.objects.get_or_create(ski_area_network=skiarea_network, member=skiarea, valid_from=form.cleaned_data["valid_from"], valid_to=form.cleaned_data["valid_until"])
            if created:
                messages.success(request, f"Successfully assigned ski area {skiarea} to network {skiarea_network}")
            else:
                messages.warning(request, f"Ski area {skiarea} already assigned to network {skiarea_network}")
            return redirect("sync_osm")
        else:
            messages.error(request, f"Error assigning ski area to network: {form.errors}")
    return redirect("sync_osm")


class SkiAreaAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return SkiArea.objects.none()

        qs = SkiArea.objects.filter(~Q(name__icontains="unnamed"), way__isnull=False)
        
        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs
    

class SkiAreaNetworkAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return SkiAreaNetwork.objects.none()

        qs = SkiAreaNetwork.objects.filter(~Q(name__icontains="unnamed"))
        
        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs    
