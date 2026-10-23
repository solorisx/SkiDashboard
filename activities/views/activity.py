import logging
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.core.serializers import serialize
from django.contrib.gis.geos import LineString, Point
from django.db.models import F, Q, Exists, OuterRef
from django.db.models.functions import Round
from django.contrib.gis.db.models.functions import AsGeoJSON, Centroid
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from itertools import groupby
from operator import attrgetter
import os

# Conditionally import silk_profile only if Silk is enabled
if os.getenv("ENABLE_SILK", "false").lower() == "true":
    from silk.profiling.profiler import silk_profile
else:
    # No-op decorator when Silk is disabled
    def silk_profile(name=None):
        def decorator(func):
            return func

        return decorator


from activities.models import LiftRide, PisteRide
from cost.models import SeasonPass
from osm.models import Aerialway, Piste, PisteSegment, SkiArea
from osm.osm_util import get_aerialways_with_distance

from ..models import Activity
from ..utils.queries import get_user_activities_base_query
from ..utils.seasons import get_seasons, parse_season_string

logger = logging.getLogger(__name__)


def get_unique_lift_rides(activity):
    """Get count of unique lift rides for an activity."""
    return activity.laps.lift_rides.values("aerialway").distinct().count()


@login_required
@silk_profile(name="activity_list")
def activity_list(request):
    """Show all activities with pagination, cost management, filtering and grouping."""
    logger.debug(f"Request method: {request.method}")

    # Check for delete success message
    if request.GET.get("deleted") == "1":
        from django.contrib import messages

        messages.success(request, "Activity deleted successfully!")

    # Get filter parameters
    ski_area_filter = request.GET.get("ski_area")
    season_filter = request.GET.get("season")
    group_by_ski_area = request.GET.get("group_by") == "ski_area"
    group_sort = request.GET.get("group_sort", "name")  # 'name' or 'visits'

    activities = get_user_activities_base_query(request.user).order_by("-timestamp")

    # Apply ski area filter if specified
    if ski_area_filter:
        try:
            ski_area_id = int(ski_area_filter)
            activities = activities.filter(ski_area_id=ski_area_id)
        except (ValueError, TypeError):
            # Invalid ski_area parameter, ignore it
            pass

    # Apply season filter if specified
    if season_filter:
        try:
            start_date, end_date = parse_season_string(season_filter, request.user)
            if start_date and end_date:
                activities = activities.filter(timestamp__range=[start_date, end_date])
        except (ValueError, TypeError):
            # Invalid season parameter, ignore it
            pass

    # Create a subquery to check for valid season passes
    season_pass_subquery = SeasonPass.objects.filter(
        user=request.user, valid_from__lte=OuterRef("timestamp__date"), valid_until__gte=OuterRef("timestamp__date")
    ).filter(
        Q(skiarea=OuterRef("ski_area"))  # Direct ski area match
        | Q(skiarea_network__members__member=OuterRef("ski_area"))  # Ski area network match through members
    )

    activities = activities.annotate(
        total_distance_km=Round(F("total_distance") / 1000, 2),
        has_season_pass=Exists(season_pass_subquery),
    )

    # Get available ski areas and seasons for the filter dropdowns
    available_ski_areas = SkiArea.objects.filter(activity__user=request.user).distinct().order_by("name")

    available_seasons = get_seasons(request.user)

    # Pre-calculate selected ski area to avoid O(n) template lookups
    selected_ski_area = None
    if ski_area_filter:
        try:
            ski_area_id = int(ski_area_filter)
            selected_ski_area = SkiArea.objects.get(id=ski_area_id)
        except (ValueError, TypeError, SkiArea.DoesNotExist):
            pass

    # Handle grouping by ski area
    if group_by_ski_area:
        # Must order by ski_area__name first so groupby works correctly
        all_activities_query = activities.order_by("ski_area__name", "-timestamp")
        total_count = all_activities_query.count()

        # Group all activities first to avoid splitting groups across pages
        all_activities = list(all_activities_query)
        all_grouped_activities = []
        for ski_area, group in groupby(all_activities, key=attrgetter("ski_area")):
            activities_list = list(group)
            all_grouped_activities.append(
                {"ski_area": ski_area, "activities": activities_list, "count": len(activities_list)}
            )

        if group_sort == "visits":
            all_grouped_activities.sort(key=lambda g: g["count"], reverse=True)

        # paginate by complete groups
        groups_per_page = 5  # Show 5 complete ski area groups per page
        group_paginator = Paginator(all_grouped_activities, groups_per_page)
        page_number = request.GET.get("page", 1)
        page_obj = group_paginator.get_page(page_number)

        grouped_activities = page_obj.object_list

        # Get all activity IDs on this page across all groups
        activity_ids = []
        for group in grouped_activities:
            activity_ids.extend([act.id for act in group["activities"]])

        # Add geometry annotations only for activities on this page (much faster!)
        # Need to fetch with all the same annotations to preserve existing data
        if activity_ids:
            paginated_activities = (
                get_user_activities_base_query(request.user)
                .filter(id__in=activity_ids)
                .annotate(
                    total_distance_km=Round(F("total_distance") / 1000, 2),
                    has_season_pass=Exists(season_pass_subquery),
                    geom_geojson=AsGeoJSON("geom"),
                    geom_centroid=Centroid("geom"),
                )
            )

            # Create a dict for fast lookup and replace activities in groups
            activity_dict = {act.id: act for act in paginated_activities}
            for group in grouped_activities:
                group["activities"] = [activity_dict.get(act.id, act) for act in group["activities"]]

        context = {
            "grouped_activities": grouped_activities,
            "is_grouped": True,
            "available_ski_areas": available_ski_areas,
            "available_seasons": available_seasons,
            "current_ski_area_filter": ski_area_filter,
            "current_season_filter": season_filter,
            "selected_ski_area": selected_ski_area,
            "total_activities": total_count,
            "group_sort": group_sort,
            "page_obj": page_obj,  # Include pagination info for grouped mode
        }
    else:
        # Regular pagination
        paginator = Paginator(activities, 12)  # Show 12 activities per page (works as 1×12, 2×6, 3×4 rows)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        # Add geometry annotations only for activities on this page (much faster!)
        # Need to fetch with all the same annotations to preserve existing data
        activity_ids = [activity.id for activity in page_obj]
        paginated_activities = (
            get_user_activities_base_query(request.user)
            .filter(id__in=activity_ids)
            .annotate(
                total_distance_km=Round(F("total_distance") / 1000, 2),
                has_season_pass=Exists(season_pass_subquery),
                geom_geojson=AsGeoJSON("geom"),
                geom_centroid=Centroid("geom"),
            )
        )

        # Replace page_obj items with fully annotated versions, preserving order
        activity_dict = {act.id: act for act in paginated_activities}
        page_obj.object_list = [activity_dict[aid] for aid in activity_ids if aid in activity_dict]

        context = {
            "page_obj": page_obj,
            "is_grouped": False,
            "available_ski_areas": available_ski_areas,
            "available_seasons": available_seasons,
            "current_ski_area_filter": ski_area_filter,
            "current_season_filter": season_filter,
            "selected_ski_area": selected_ski_area,
        }

    return render(request, "activities/activity_list.html", context)


@login_required
def activity_detail(request, activity_id):
    """Show details of a single activity, including laps and lift rides."""
    try:
        # Create a subquery to check for valid season passes
        season_pass_subquery = SeasonPass.objects.filter(
            user=request.user, valid_from__lte=OuterRef("timestamp__date"), valid_until__gte=OuterRef("timestamp__date")
        ).filter(
            Q(skiarea=OuterRef("ski_area"))  # Direct ski area match
            | Q(skiarea_network__members__member=OuterRef("ski_area"))  # Ski area network match through members
        )

        activity = Activity.objects.annotate(
            total_distance_km=Round(F("total_distance") / 1000.0, 2),
            has_season_pass=Exists(season_pass_subquery),
        ).get(id=activity_id, user=request.user)
    except Activity.DoesNotExist:
        raise Http404("Activity not found")

    laps = activity.laps.all().order_by("lap_index")
    lift_rides = LiftRide.objects.filter(lap__activity=activity).order_by("lap__lap_index", "timestamp")
    piste_rides = (
        PisteRide.objects.filter(lap__activity=activity)
        .select_related("piste", "piste__way")
        .order_by("lap__lap_index", "timestamp")
    )

    # Calculate length in meters for each piste (transform from degrees to meters)
    for piste_ride in piste_rides:
        if piste_ride.piste.geom:
            # Transform to Web Mercator (EPSG:3857) for accurate length calculation
            geom_meters = piste_ride.piste.geom.transform(3857, clone=True)
            piste_ride.length_meters = int(geom_meters.length)
        else:
            piste_ride.length_meters = None

    # Filter to only show piste rides > 500m
    piste_rides = [pr for pr in piste_rides if pr.length_meters and pr.length_meters > 500]
    aerialways = Aerialway.objects.filter(liftride__lap__activity=activity).distinct()

    aerialways_dropdown = get_aerialways_with_distance(
        lat=activity.start_position.y, lon=activity.start_position.x, distance_km=20
    )
    badges = sorted(activity.badges.all(), key=lambda x: (-x.badge.rarity_order, x.badge.name))

    # Check if user has opted in to Strava write
    user_opt_in_strava_write = False
    try:
        user_opt_in_strava_write = request.user.userprofile.opt_in_strava_write
    except:
        pass

    # Calculate piste completeness for this activity
    piste_completeness = None
    if activity.ski_area:
        from activities.utils.completeness import calculate_activity_piste_completeness

        piste_completeness = calculate_activity_piste_completeness(activity)

    # Build lap chart data for elevation profile and per-lap stats
    import json as _json

    lap_chart_data = []
    for lap in laps:
        duration_secs = int(lap.total_elapsed_time.total_seconds()) if lap.total_elapsed_time else 0
        lap_chart_data.append(
            {
                "lap": lap.lap_index,
                "min_alt": round(lap.min_altitude) if lap.min_altitude is not None else None,
                "max_alt": round(lap.max_altitude) if lap.max_altitude is not None else None,
                "descent": round(lap.total_descent) if lap.total_descent is not None else None,
                "distance": round(lap.total_distance) if lap.total_distance is not None else None,
                "duration": duration_secs,
                "avg_speed_kmh": round(lap.avg_speed * 3.6, 1) if lap.avg_speed is not None else None,
                "max_speed_kmh": round(lap.max_speed * 3.6, 1) if lap.max_speed is not None else None,
                "avg_hr": lap.avg_heart_rate,
                "calories": round(lap.total_calories) if lap.total_calories is not None else None,
            }
        )

    # Find best lap (most descent)
    best_lap_index = None
    if lap_chart_data:
        best = max(lap_chart_data, key=lambda x: x["descent"] or 0)
        if best["descent"]:
            best_lap_index = best["lap"]

    return render(
        request,
        "activities/activity_detail.html",
        {
            "activity": activity,
            "laps": laps,
            "lift_rides": lift_rides,
            "piste_rides": piste_rides,
            "badges": badges,
            "aerialways": aerialways,
            "aerialways_dropdown": aerialways_dropdown,
            "user_opt_in_strava_write": user_opt_in_strava_write,
            "piste_completeness": piste_completeness,
            "lap_chart_data": _json.dumps(lap_chart_data),
            "best_lap_index": best_lap_index,
        },
    )


@login_required
def activity_detail_strava(request, strava_id):
    """Show details of a single activity from Strava ID."""
    activity = get_object_or_404(Activity, strava_id=strava_id, user=request.user)
    return redirect("activity_detail", activity_id=activity.id)


from django.contrib.admin.views.decorators import staff_member_required
import json


@staff_member_required
def activity_map(request, activity_id):
    """
    Display a map view of the activity with GPS track, lift rides, and piste rides.
    Shows pistes that met the 80% threshold and those that didn't in different colors.
    Staff only.
    """
    activity = get_object_or_404(Activity, id=activity_id)

    # Get unique lift rides
    unique_lifts = Aerialway.objects.filter(liftride__lap__activity=activity).distinct()

    # Get unique piste rides (those that met the 80% threshold)
    qualified_pistes = Piste.objects.filter(pisteride__lap__activity=activity).distinct()

    # Find pistes that intersected but didn't qualify (below 80% threshold)
    # Buffer the activity geometry to find all intersecting pistes
    if activity.geom:
        # Use same buffer as activity_parser (200 meters)
        buffer_width = 200 / 40000000 * 360  # ~200 meters in degrees
        buffered_geom = activity.geom.buffer(buffer_width)

        # Find all intersecting pistes
        all_intersecting_pistes = Piste.objects.filter(geom__intersects=buffered_geom, geom__isnull=False)

        # Exclude the ones that qualified
        below_threshold_pistes = all_intersecting_pistes.exclude(
            id__in=qualified_pistes.values_list("id", flat=True)
        ).distinct()
    else:
        below_threshold_pistes = Piste.objects.none()
        buffered_geom = None

    # Serialize lap geometries instead of full GPS track
    lap_tracks_geojson = {"type": "FeatureCollection", "features": []}
    for lap in activity.laps.all().order_by("lap_index"):
        if lap.geom:
            feature = {
                "type": "Feature",
                "geometry": json.loads(lap.geom.geojson),
                "properties": {"lap_index": lap.lap_index},
            }
            lap_tracks_geojson["features"].append(feature)

    # Calculate buffered track from lap geometries
    if lap_tracks_geojson["features"]:
        # Union all lap geometries for buffering
        from django.contrib.gis.geos import MultiLineString

        lap_geoms = [lap.geom for lap in activity.laps.all() if lap.geom]
        if lap_geoms:
            combined_geom = MultiLineString(*lap_geoms) if len(lap_geoms) > 1 else lap_geoms[0]
            buffered_geom = combined_geom.buffer(buffer_width)
            buffered_track = json.loads(buffered_geom.geojson)
        else:
            buffered_track = None
    else:
        buffered_track = None

    # Serialize unique lift geometries
    lift_rides_geojson = {"type": "FeatureCollection", "features": []}
    for lift in unique_lifts:
        if lift.geom:
            feature = {
                "type": "Feature",
                "geometry": json.loads(lift.geom.geojson),
                "properties": {"name": lift.name or "Unnamed Lift", "type": lift.aerialway_type or "Unknown"},
            }
            lift_rides_geojson["features"].append(feature)

    # Serialize qualified piste geometries (met 80% threshold)
    piste_rides_geojson = {"type": "FeatureCollection", "features": []}
    for piste in qualified_pistes:
        if piste.geom:
            feature = {
                "type": "Feature",
                "geometry": json.loads(piste.geom.geojson),
                "properties": {
                    "name": piste.name or piste.ref or "Unnamed Piste",
                    "difficulty": piste.piste_difficulty or "Unknown",
                },
            }
            piste_rides_geojson["features"].append(feature)

    # Serialize below-threshold piste geometries
    below_threshold_geojson = {"type": "FeatureCollection", "features": []}
    for piste in below_threshold_pistes:
        if piste.geom:
            feature = {
                "type": "Feature",
                "geometry": json.loads(piste.geom.geojson),
                "properties": {
                    "name": piste.name or piste.ref or "Unnamed Piste",
                    "difficulty": piste.piste_difficulty or "Unknown",
                },
            }
            below_threshold_geojson["features"].append(feature)

    return render(
        request,
        "activities/activity_map.html",
        {
            "activity": activity,
            "lap_tracks_geojson": json.dumps(lap_tracks_geojson),
            "buffered_track": json.dumps(buffered_track),
            "lift_rides_geojson": json.dumps(lift_rides_geojson),
            "piste_rides_geojson": json.dumps(piste_rides_geojson),
            "below_threshold_geojson": json.dumps(below_threshold_geojson),
            "unique_lifts_count": unique_lifts.count(),
            "unique_pistes_count": qualified_pistes.count(),
            "below_threshold_count": below_threshold_pistes.count(),
        },
    )


def swap_coords(geom):
    """Swap lat/lon if needed (for GeoJSON compatibility)."""
    if geom.geom_type == "Point":
        return Point(geom.y, geom.x, srid=4326)
    elif geom.geom_type == "LineString":
        return LineString([(p[1], p[0]) for p in geom.coords], srid=4326)
    return geom


@login_required
def segment_map(request, activity_id):
    """Display segment map for an activity."""
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)

    # Ensure activity geometry is in EPSG:4326
    if activity.geom.srid != 4326:
        activity.geom.transform(4326)

    # Serialize activity geometry
    way_geojson = serialize("geojson", [activity], geometry_field="geom")

    # Get actual piste segment geometries
    piste_segments = PisteSegment.objects.filter(id__in=activity.piste_segments.values_list("piste_segment", flat=True))

    skiarea = activity.ski_area
    pistes = Piste.objects.filter(geom__coveredby=skiarea.geom)

    # Serialize segment geometries
    segments_geojson = serialize("geojson", piste_segments, geometry_field="geom")
    piste_geojson = serialize("geojson", pistes, geometry_field="geom")

    return render(
        request,
        "segment_map.html",
        {
            "activity_id": activity.strava_id,
            "way_geojson": way_geojson,
            "segments_geojson": segments_geojson,
            "piste_geojson": piste_geojson,
        },
    )


class ActivityAPI(LoginRequiredMixin, View):
    """API endpoint to delete and update activity."""

    def patch(self, request, activity_id):
        """Handle PATCH requests to update an activity."""
        import json

        try:
            activity = get_object_or_404(Activity, id=activity_id, user=request.user)
            data = json.loads(request.body)

            # Update activity name if provided
            if "name" in data:
                new_name = data["name"].strip()
                if not new_name:
                    return JsonResponse({"success": False, "error": "Activity name cannot be empty"}, status=400)
                if len(new_name) > 100:
                    return JsonResponse(
                        {"success": False, "error": "Activity name cannot exceed 100 characters"}, status=400
                    )

                old_name = activity.name
                activity.name = new_name
                activity.manually_modified = True
                activity.save()

                logging.getLogger(__name__).info(
                    f"Activity name updated from '{old_name}' to '{new_name}' (ID: {activity_id}) by user {request.user}"
                )

                return JsonResponse(
                    {"success": True, "name": activity.name, "message": "Activity name updated successfully"}
                )

            return JsonResponse({"success": False, "error": "No valid fields to update"}, status=400)

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        except Exception as e:
            logging.getLogger(__name__).error(f"Error updating activity {activity_id}: {e}")
            return JsonResponse({"success": False, "error": "Server error"}, status=500)

    def delete(self, request, activity_id):
        """Handle DELETE requests to delete an activity."""
        activity = get_object_or_404(Activity, id=activity_id, user=request.user)
        activity_name = activity.name
        skiarea_id = activity.ski_area.id if activity.ski_area else None
        activity.delete()
        from activities.tasks import recalculate_completeness_task

        recalculate_completeness_task.delay(user_id=request.user.id, skiarea_id=skiarea_id)
        logging.getLogger(__name__).info(
            f"Activity '{activity_name}' (ID: {activity_id}) deleted by user {request.user}"
        )
        return JsonResponse(
            {"success": True, "message": f"Activity '{activity_name}' deleted successfully"}, status=204
        )


@login_required
def generate_share_image(request, activity_id):
    """
    Generate and download a shareable Instagram story-sized image for an activity.

    Returns a PNG image with activity details, mini map, and statistics.
    """
    from ..utils.image_generator import generate_activity_share_image_bytes

    # Get activity and verify ownership
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)

    try:
        # Generate the image
        img_bytes = generate_activity_share_image_bytes(activity)

        # Create filename
        activity_name_slug = activity.name.replace(" ", "_")[:30] if activity.name else "activity"
        filename = f"{activity_name_slug}_{activity_id}_share.png"

        # Return as downloadable PNG
        response = HttpResponse(img_bytes.read(), content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        logger.info(f"Generated share image for activity {activity_id} by user {request.user}")
        return response

    except Exception as e:
        logger.error(f"Error generating share image for activity {activity_id}: {e}")
        return HttpResponse("Error generating share image. Please try again later.", status=500)
