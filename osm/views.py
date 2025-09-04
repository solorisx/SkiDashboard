from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import OSMSyncForm, OSMFileSyncForm, SkiAreaNetworkForm, SegmentUpdateForm

from .models import SkiArea, SkiAreaNetwork, SkiAreaNetworkMember, Way, Piste, PisteSegment, Node, Station, Aerialway
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.serializers import serialize
from django.db.models import Q
import logging
from dal import autocomplete
from django.http import HttpResponseNotFound

from .osm_downloader import load_osm
from .osm_parser import parse_osm_file
from .osm_interface import load_osm_data
from .osm_segments import update_piste_segments
from .tasks import parse_osm_file_task


logger = logging.getLogger('core')


@staff_member_required
def sync_osm(request):    
    form1 = OSMSyncForm()
    form2 = OSMFileSyncForm()
    form3 = SkiAreaNetworkForm()
    form4 = SegmentUpdateForm()

    # Get database counts
    db_stats = {
        'ski_areas': SkiArea.objects.count(),
        'ski_area_networks': SkiAreaNetwork.objects.count(),
        'ski_area_network_members': SkiAreaNetworkMember.objects.count(),
        'ways': Way.objects.count(),
        'pistes': Piste.objects.count(),
        'aerialways': Aerialway.objects.count(),
        'stations': Station.objects.count(),
        'nodes': Node.objects.count(),
    }

    return render(request, "admin/osm-admin.html", {"form1": form1, "form2": form2, "form3": form3, "form4": form4, "db_stats": db_stats})
    

@staff_member_required
def sync_osm_api(request):
    if request.method == "POST":
        form = OSMSyncForm(request.POST)
        if form.is_valid():
            osm_id = form.cleaned_data["osm_id"]
            osm_type = form.cleaned_data["osm_type"]
            try:
                load_osm_data(osm_id, osm_type)
                raise NotImplementedError("OSM API sync not implemented.")
                messages.success(request, f"Successfully loaded OSM data for {osm_type} {osm_id}.")
            except Exception as e:
                messages.error(request, f"Error loading OSM data: {e}")
            return redirect("sync_osm")
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
                parse_osm_file_task.delay("planet_pistes-osmium.osm", [sync_nodes, sync_ways, sync_relations, sync_areas])
                messages.success(request, f"Successfully initiated loading OSM data from file.")
                return redirect("sync_osm")
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
    
@login_required
def map(request, osm_id):
    way = get_object_or_404(Way, osm_id=osm_id)
    piste = Piste.objects.filter(way=way).first()
    if not piste:
        return HttpResponseNotFound(f"No piste found for way {way}")
    if piste.is_geom_outdated:
        piste.generate_segments(regenerate=True)
        logger.debug(f"Updated geometry for piste {piste}")
    if not piste.segments.all():
        logger.debug(f"No segments for piste {piste}")
        piste.generate_segments()
        logger.debug(f"Generated segments for piste {piste}")
    nodes = piste.way.nodes.all()
    way_geojson = serialize("geojson", [piste], geometry_field="geom")
    segments_geojson = serialize("geojson", PisteSegment.objects.filter(piste=piste), geometry_field="geom")
    nodes_geojson = serialize("geojson", nodes, geometry_field="geom")

    return render(request, "map.html", {
        "osm_id": osm_id,
        "way_geojson": way_geojson,
        "segments_geojson": segments_geojson,
        "nodes_geojson": nodes_geojson
    })


def segment_map(request, osm_id):
    area = get_object_or_404(SkiArea, osm_id=osm_id)
    segments = PisteSegment.objects.filter(geom__coveredby=area.geom)
    pistes = Piste.objects.filter(geom__coveredby=area.geom)
    boundary_geojson = serialize("geojson", [area], geometry_field="geom")
    segments_geojson = serialize("geojson", segments, geometry_field="geom")
    pistes_geojson = serialize("geojson", pistes, geometry_field="geom")

    return render(request, "area_segment_map.html", {
        "ski_area": area,
        "osm_id": osm_id,
        "pistes_geojson": pistes_geojson,
        "segments_geojson": segments_geojson,
        "boundary_geojson": boundary_geojson
    })


@staff_member_required
def update_segments(request, osm_id=None):
    try:
        update_piste_segments(osm_id)
        messages.success(request, f"Updated segments for piste {osm_id}")
    except Exception as e:
        messages.error(request, f"Error updating segments: {e}")
    return redirect("sync_osm")
