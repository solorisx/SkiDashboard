import json
import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.serializers import serialize
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from dal import autocomplete

from .forms import (
    OSMSyncForm,
    OSMFileSyncForm,
    SkiAreaNetworkForm,
    SegmentUpdateForm,
    PisteGeometryUpdateForm,
)
from .models import (
    Aerialway,
    Node,
    Piste,
    PisteSegment,
    SkiArea,
    SkiAreaNetwork,
    SkiAreaNetworkMember,
    Station,
    Way,
)
from .osm_interface import load_osm_data
from .osm_segments import update_piste_segments
from .tasks import parse_osm_file_task, update_piste_geometry_task


logger = logging.getLogger('core')


@staff_member_required
def sync_osm(request):
    form1 = OSMSyncForm()
    form2 = OSMFileSyncForm()
    form3 = SkiAreaNetworkForm()
    form4 = SegmentUpdateForm()
    form5 = PisteGeometryUpdateForm()

    # Get database counts
    db_stats = {
        'ski_areas': SkiArea.objects.count(),
        'ski_area_networks': SkiAreaNetwork.objects.count(),
        'ski_area_network_members': SkiAreaNetworkMember.objects.count(),
        'ways': Way.objects.count(),
        'pistes': Piste.objects.count(),
        'pistes_without_geom': Piste.objects.filter(geom__isnull=True).count(),
        'aerialways': Aerialway.objects.count(),
        'stations': Station.objects.count(),
        'nodes': Node.objects.count(),
    }

    return render(request, "admin/osm-admin.html", {"form1": form1, "form2": form2, "form3": form3, "form4": form4, "form5": form5, "db_stats": db_stats})
    

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

        if not self.request.user.is_authenticated:
            return SkiArea.objects.none()

        qs = SkiArea.objects.filter(~Q(name__icontains="unnamed"), way__isnull=False)
        
        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs.order_by("name")[:25]

class SkiAreaNetworkAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):

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


@staff_member_required
def update_piste_geometry(request):
    """Update geometry for pistes that don't have it."""
    if request.method == "POST":
        form = PisteGeometryUpdateForm(request.POST)
        if form.is_valid():
            ski_area = form.cleaned_data.get("ski_area")
            ski_area_id = ski_area.id if ski_area else None

            # Get count of pistes to update
            pistes_query = Piste.objects.filter(geom__isnull=True)
            if ski_area_id:
                pistes_query = pistes_query.filter(way__skiarea__id=ski_area_id)
            piste_count = pistes_query.count()

            # Launch async task
            try:
                update_piste_geometry_task.delay(ski_area_id)
                if ski_area:
                    messages.success(request, f"Initiated geometry update for {piste_count} pistes in {ski_area.name}. Task is running in the background.")
                else:
                    messages.success(request, f"Initiated geometry update for {piste_count} pistes across all ski areas. Task is running in the background.")
            except Exception as e:
                messages.error(request, f"Error initiating geometry update: {e}")
        else:
            messages.error(request, f"Form validation error: {form.errors}")
        return redirect("sync_osm")
    return redirect("sync_osm")


@method_decorator(staff_member_required, name="dispatch")
class SkiAreaNetworkUploadView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'admin/skiarea_network_upload.html')

    def post(self, request, *args, **kwargs):
        if 'json_file' not in request.FILES:
            messages.error(request, "No JSON file uploaded.")
            return redirect("skiarea_network_upload")

        json_file = request.FILES['json_file']
        if not json_file.name.endswith('.json'):
            messages.error(request, "Uploaded file is not a JSON file.")
            return redirect("skiarea_network_upload")
        
        try:
            data = json_file.read().decode('utf-8')
            result = self.process_data(data)
            if result and (result['created'] > 0 or result['updated'] > 0):
                messages.success(request, f"Successfully created {result['created']} and updated {result['updated']} ski area networks.")
                return redirect("skiarea_network_upload")
            else:
                messages.error(request, "No new ski area networks were created.")
                return redirect("skiarea_network_upload")
        except Exception as e:
            messages.error(request, f"Error processing file: {e}")
            raise e
            return redirect("skiarea_network_upload")
        
    def process_data(self, data):
        """ Process the uploaded JSON data and create SkiAreaNetwork entries.
        Args:
            data (str): JSON string containing ski area network data. Expected format:
                "networks": [
                    {
                        "name": "Network Name",
                        "id":   123,
                        "members":
                            [
                            {
                                "osm_id": 12345,
                                "name": "Ski Area Name",
                                "valid_from": "2023-01-01",
                                "valid_until": "2023-12-31"
                            },
                            ...
                        ]
                    },
                    ...
                ]
        """

        created_networks = 0
        updated_networks = 0
        created_members = 0

        try:
            networks = json.loads(data).get('networks', [])
            if not networks:
                return {'created': created_networks, 'error': "No networks found in JSON data."}
            for net in networks:

                with transaction.atomic():
                    if net.get('id'):
                        skiarea_network = SkiAreaNetwork.objects.filter(id=net['id']).first()
                        if not skiarea_network:
                            raise json.JSONDecodeError(f"SkiAreaNetwork with id {net['id']} not found.", data, 0)
                    elif net.get('name'):
                        skiarea_network, created = SkiAreaNetwork.objects.get_or_create(name=net['name'])
                        if created:
                            created_networks += 1
                        else:
                            updated_networks += 1
                            skiarea_network.members.all().delete()  # Clear existing members to avoid duplicates
                    else:
                        raise json.JSONDecodeError("Network must have at least an 'id' or 'name' field.", data, 0)

                    for member in net.get('members', []):
                        if member.get('osm_id'):
                            skiarea = SkiArea.objects.filter(osm_id=member['osm_id'])
                            if not skiarea.exists():
                                logger.warning(f"SkiArea with OSM ID {member['osm_id']} not found.")
                        elif member.get('name'):
                            skiarea = SkiArea.objects.filter(name__icontains=member['name'])
                            if not skiarea.exists():
                                logger.warning(f"SkiArea with name containing '{member['name']}' not found.")
                        else:
                            raise json.JSONDecodeError("Member must have at least an 'osm_id' or 'name' field.", data, 0)
                        
                        valid_from = member.get('valid_from')
                        valid_until = member.get('valid_until')
                        max_days = member.get('max_days', 365)

                        for skiarea in skiarea:
                            _, created = SkiAreaNetworkMember.objects.get_or_create(
                                ski_area_network=skiarea_network,
                                member=skiarea,
                                valid_from=valid_from,
                                valid_to=valid_until,
                                max_days=max_days
                            )
                            if created:
                                logger.debug(f"Added {skiarea} to network {skiarea_network}")
                                created_members += 1

            return {'created': created_networks, 'updated': updated_networks, 'members_created': created_members}

        except Exception as e:
            logger.error(f"Error processing ski area network data: {e}")
            return {'created': created_networks, 'error': str(e)}


