import logging
from django.core.cache import cache
from django.db.models import Count

from activities.models import LiftRide
from osm.models import Aerialway, SkiArea, LiftFilterConfig

logger = logging.getLogger(__name__)


def _find_lifts_by_constructed_geometry(ski_area, boundary_geom, user=None):
    """Helper function to find lifts using constructed geometry intersection."""
    try:
        # First try to get a reasonable subset of aerialways near this ski area
        # Use a bounding box to limit the search space
        bbox = boundary_geom.envelope

        # Find lifts whose constructed geometry intersects with the boundary
        lift_ids = []

        # Query aerialways that might be in the area (using way node coordinates as proxy)
        from django.db import connection
        with connection.cursor() as cursor:
            # Get aerialways whose ways have nodes within the bounding box
            cursor.execute("""
                SELECT DISTINCT a.id, a.name
                FROM osm_aerialway a
                JOIN osm_way w ON a.way_id = w.id
                JOIN osm_waynode wn ON w.id = wn.way_id
                JOIN osm_node n ON wn.node_id = n.id
                WHERE ST_Within(n.geom, ST_GeomFromText(%s, 4326))
                LIMIT 100
            """, [bbox.wkt])

            candidate_aerialways = cursor.fetchall()

        logger.info(f"Checking {len(candidate_aerialways)} candidate aerialways for intersection with ski area {ski_area.id}")

        for aerialway_id, aerialway_name in candidate_aerialways:
            try:
                aerialway = Aerialway.objects.get(id=aerialway_id)
                # Apply lift type filtering with user preferences
                if not LiftFilterConfig.should_include_lift(aerialway.aerialway, user=user):
                    continue
                if aerialway.way and aerialway.way.constructed_geom:
                    if boundary_geom.intersects(aerialway.way.constructed_geom):
                        lift_ids.append(aerialway.id)
            except Aerialway.DoesNotExist:
                continue

        if lift_ids:
            lifts = Aerialway.objects.filter(id__in=lift_ids)
            logger.info(f"Found {len(lift_ids)} lifts using constructed geometry intersection for ski area {ski_area.id} (after filtering)")
            return lifts
        else:
            return Aerialway.objects.none()

    except Exception as e:
        logger.warning(f"Error in constructed geometry search for ski area {ski_area.id}: {e}")
        return Aerialway.objects.none()


def get_available_lifts_in_ski_area(ski_area, user=None):
    """Get all available lifts in a ski area, respecting user exclusions."""
    try:
        lifts = Aerialway.objects.none()

        # First try direct geometry intersection if aerialways have geometries
        if ski_area.geom:
            # Check if any aerialways have geometry for spatial intersection
            aerialways_with_geom = Aerialway.objects.exclude(geom__isnull=True).exists()
            if aerialways_with_geom:
                lifts = LiftFilterConfig.filter_lifts_queryset(
                    Aerialway.objects.filter(geom__intersects=ski_area.geom),
                    user=user
                ).distinct()
                logger.info(f"Using direct geometry intersection for ski area {ski_area.id}")
            else:
                # No aerialway geometries, try constructed geometry approach
                logger.info(f"No aerialway geometries available, using constructed geometry for ski area {ski_area.id}")
                lifts = _find_lifts_by_constructed_geometry(ski_area, ski_area.geom, user)

        # If no lifts found yet and we have a boundary way, try constructed geometry
        if not lifts.exists() and ski_area.way:
            boundary_geom = ski_area.way.constructed_geom
            logger.info(f"Ski area {ski_area.id} has way {ski_area.way.osm_id}, constructed_geom: {type(boundary_geom)}")
            if boundary_geom:
                lifts = _find_lifts_by_constructed_geometry(ski_area, boundary_geom, user)

        # If still no lifts found, try way relationships as fallback
        if not lifts.exists():
            lifts = LiftFilterConfig.filter_lifts_queryset(
                Aerialway.objects.filter(way__ski_areas=ski_area),
                user=user
            ).distinct()
            if lifts.exists():
                logger.info(f"Found {lifts.count()} lifts using way relationships for ski area {ski_area.id} (after filtering)")
            else:
                logger.info(f"No lifts found via way relationships for ski area {ski_area.id}")

        # some areas exist twice, try to find second instance
        if not lifts.exists():
            duplicate_areas = SkiArea.objects.filter(name=ski_area.name).exclude(id=ski_area.id)
            logger.info(f"No lifts found via geometry/way relationships for ski area {ski_area.id}, checking {duplicate_areas.count()} duplicate areas")
            for dup in duplicate_areas:
                if dup.geom:
                    lifts = LiftFilterConfig.filter_lifts_queryset(
                        Aerialway.objects.filter(geom__intersects=dup.geom),
                        user=user
                    ).distinct()
                elif dup.way:
                    lifts = LiftFilterConfig.filter_lifts_queryset(
                        Aerialway.objects.filter(way__ski_areas=dup),
                        user=user
                    ).distinct()
                if lifts.exists():
                    logger.info(f"Found lifts for ski area {ski_area.id} using duplicate area {dup.id} (after filtering)")
                    break

        # If no lifts found through spatial/way relationships,
        # include lifts that users have actually ridden in this ski area
        # this will only really work once there is enough user data
        if not lifts.exists():
            logger.info(f"No lifts found via geometry/way relationships for ski area {ski_area.id}, checking actual ride data")
            ridden_lift_ids = LiftRide.objects.filter(
                lap__activity__ski_area=ski_area
            ).values_list('aerialway', flat=True).distinct()

            if ridden_lift_ids:
                lifts = LiftFilterConfig.filter_lifts_queryset(
                    Aerialway.objects.filter(id__in=ridden_lift_ids),
                    user=user
                )
                logger.info(f"Found {lifts.count()} lifts from actual ride data for ski area {ski_area.id} (after filtering)")

        return lifts
    except Exception as e:
        logger.warning(f"Error finding lifts in ski area {ski_area.id}: {e}")
        # Fallback to empty queryset
        return Aerialway.objects.none()


def calculate_ski_area_completeness(user, ski_area, force_calc=False, season=None):
    """
    Calculate completeness statistics for a user in a specific ski area.
    Gets recalculated if force_calc is True which is used on activity import.

    Args:
        user: User object
        ski_area: SkiArea object
        force_calc: Whether to force recalculation
        season: Optional season string (e.g., "2023-2024") for season-specific filtering

    Returns:
        dict: Completeness statistics including percentages and counts
    """
    logger.debug(f"Calculating completeness for user {user.id} in ski area {ski_area.id}, force_calc={force_calc}, season={season}")
    
    # Include season in cache key if specified
    cache_key = f"completeness_{user.id}_{ski_area.id}"
    if season:
        cache_key += f"_{season}"

    if not force_calc:
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.debug(f"Using cached completeness for user {user.id} in ski area {ski_area.id}, season: {season}")
            return cached_result

    # Get all available lifts in the ski area (with user exclusions)
    available_lifts = get_available_lifts_in_ski_area(ski_area, user=user)
    total_lifts = available_lifts.count()

    if total_lifts == 0:
        result = {
            'total_available': 0,
            'total_ridden': 0,
            'completion_percentage': 0,
            'lifts_ridden': [],
            'lifts_not_ridden': [],
            'lift_type_breakdown': {}
        }
        cache.set(cache_key, result, 3600)  # Cache for 1 hour
        return result

    # Get lifts the user has ridden (with optional season filtering)
    user_lift_rides_query = LiftRide.objects.filter(
        lap__activity__user=user,
        lap__activity__ski_area=ski_area,
        aerialway__in=available_lifts
    )

    # Apply season filtering if specified
    if season:
        from ..utils.seasons import parse_season_string
        season_start, season_end = parse_season_string(season, user=user)
        if season_start and season_end:
            user_lift_rides_query = user_lift_rides_query.filter(
                lap__activity__start_time__gte=season_start,
                lap__activity__start_time__lte=season_end
            )

    user_lift_rides = user_lift_rides_query.values_list('aerialway', flat=True).distinct()

    ridden_lifts = available_lifts.filter(id__in=user_lift_rides)
    not_ridden_lifts = available_lifts.exclude(id__in=user_lift_rides)

    # Calculate lift type breakdown
    lift_type_breakdown = {}
    for lift in available_lifts:
        lift_type = getattr(lift, 'aerialway', 'unknown')
        if lift_type not in lift_type_breakdown:
            lift_type_breakdown[lift_type] = {
                'total': 0,
                'ridden': 0,
                'percentage': 0
            }
        lift_type_breakdown[lift_type]['total'] += 1

        if lift.id in user_lift_rides:
            lift_type_breakdown[lift_type]['ridden'] += 1

    # Calculate percentages for lift types
    for lift_type_data in lift_type_breakdown.values():
        if lift_type_data['total'] > 0:
            lift_type_data['percentage'] = round(
                (lift_type_data['ridden'] / lift_type_data['total']) * 100, 1
            )

    completion_percentage = round((len(user_lift_rides) / total_lifts) * 100, 1)
    logger.debug(f"User {user.id} completeness in Ski Area {ski_area.id} (season: {season}): {completion_percentage}%")

    result = {
        'total_available': total_lifts,
        'total_ridden': len(user_lift_rides),
        'completion_percentage': completion_percentage,
        'lifts_ridden': list(ridden_lifts.values('id', 'name')),
        'lifts_not_ridden': list(not_ridden_lifts.values('id', 'name')),
        'lift_type_breakdown': lift_type_breakdown
    }

    cache.set(cache_key, result, None)  # Cache indefinitely, clear on data change
    return result


def calculate_overall_completeness(user):
    """
    Calculate overall completeness across all visited ski areas for a user.

    Returns:
        dict: Overall completeness statistics
    """
    cache_key = f"overall_completeness_{user.id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    # Get all ski areas the user has visited
    visited_ski_areas = SkiArea.objects.filter(
        activity__user=user
    ).distinct()

    if not visited_ski_areas.exists():
        result = {
            'total_ski_areas': 0,
            'total_lifts_available': 0,
            'total_lifts_ridden': 0,
            'overall_percentage': 0,
            'ski_area_breakdown': []
        }
        cache.set(cache_key, result, 3600)
        return result

    ski_area_breakdown = []
    total_lifts_available = 0
    total_lifts_ridden = 0

    for ski_area in visited_ski_areas:
        completeness = calculate_ski_area_completeness(user, ski_area)
        ski_area_breakdown.append({
            'ski_area_id': ski_area.id,
            'ski_area_name': ski_area.name,
            'completeness': completeness
        })
        total_lifts_available += completeness['total_available']
        total_lifts_ridden += completeness['total_ridden']

    overall_percentage = 0
    if total_lifts_available > 0:
        overall_percentage = round((total_lifts_ridden / total_lifts_available) * 100, 1)

    result = {
        'total_ski_areas': visited_ski_areas.count(),
        'total_lifts_available': total_lifts_available,
        'total_lifts_ridden': total_lifts_ridden,
        'overall_percentage': overall_percentage,
        'ski_area_breakdown': ski_area_breakdown
    }

    # Cache for 1 hour
    cache.set(cache_key, result, 3600)
    return result


def calculate_activity_completeness(activity):
    """
    Calculate completeness for a single activity.

    Returns:
        dict: Activity-specific completeness stats
    """
    if not activity.ski_area:
        return {
            'lifts_used_today': 0,
            'total_lifts_available': 0,
            'daily_completion_percentage': 0,
            'new_lifts_discovered': 0
        }

    # Get lifts used in this activity
    activity_lifts = LiftRide.objects.filter(
        lap__activity=activity
    ).values_list('aerialway', flat=True).distinct()

    # Get all available lifts in the ski area (with user exclusions)
    available_lifts = get_available_lifts_in_ski_area(activity.ski_area, user=activity.user)
    total_available = available_lifts.count()

    # Calculate daily completion percentage
    daily_percentage = 0
    if total_available > 0:
        daily_percentage = round((len(activity_lifts) / total_available) * 100, 1)

    # Calculate new lifts discovered (lifts not ridden before this activity)
    previous_lifts = LiftRide.objects.filter(
        lap__activity__user=activity.user,
        lap__activity__ski_area=activity.ski_area,
        lap__activity__start_time__lt=activity.start_time
    ).values_list('aerialway', flat=True).distinct()

    new_lifts = set(activity_lifts) - set(previous_lifts)

    return {
        'lifts_used_today': len(activity_lifts),
        'total_lifts_available': total_available,
        'daily_completion_percentage': daily_percentage,
        'new_lifts_discovered': len(new_lifts)
    }


def calculate_batch_activity_completeness(activities, user):
    """
    Calculate completeness for multiple activities efficiently by batching operations.

    Args:
        activities: List of Activity objects (should be prefetched with laps__lift_rides)
        user: User object

    Returns:
        dict: Mapping of activity_id to completeness data
    """
    from collections import defaultdict
    from django.core.cache import cache

    if not activities:
        return {}

    # Group activities by ski area to avoid duplicate lift calculations
    activities_by_ski_area = defaultdict(list)
    for activity in activities:
        if activity.ski_area:
            activities_by_ski_area[activity.ski_area.id].append(activity)

    # Pre-calculate available lifts for each unique ski area
    ski_area_lifts_cache = {}
    for ski_area_id in activities_by_ski_area.keys():
        cache_key = f"ski_area_lifts_{ski_area_id}_{user.id}"
        cached_lifts = cache.get(cache_key)

        if cached_lifts is not None:
            ski_area_lifts_cache[ski_area_id] = cached_lifts
        else:
            # Get ski area and calculate lifts
            ski_area = activities_by_ski_area[ski_area_id][0].ski_area
            available_lifts = get_available_lifts_in_ski_area(ski_area, user=user)
            available_lift_ids = set(available_lifts.values_list('id', flat=True))
            ski_area_lifts_cache[ski_area_id] = available_lift_ids
            # Cache for 30 minutes
            cache.set(cache_key, available_lift_ids, 1800)

    # Get all lift rides for all activities in batch
    activity_ids = [a.id for a in activities]
    all_lift_rides = LiftRide.objects.filter(
        lap__activity_id__in=activity_ids
    ).values('lap__activity_id', 'aerialway').distinct()

    # Group lift rides by activity
    activity_lifts = defaultdict(set)
    for ride in all_lift_rides:
        activity_lifts[ride['lap__activity_id']].add(ride['aerialway'])

    # Pre-calculate previous lifts for new lifts discovery (batch query)
    previous_lifts_by_ski_area = {}
    for ski_area_id, ski_area_activities in activities_by_ski_area.items():
        # Get earliest activity timestamp for this ski area
        earliest_timestamp = min(a.start_time for a in ski_area_activities)

        cache_key = f"previous_lifts_{user.id}_{ski_area_id}_{earliest_timestamp.isoformat()}"
        cached_previous = cache.get(cache_key)

        if cached_previous is not None:
            previous_lifts_by_ski_area[ski_area_id] = cached_previous
        else:
            # Get all lifts ridden before the earliest activity in this batch
            previous_lifts = LiftRide.objects.filter(
                lap__activity__user=user,
                lap__activity__ski_area_id=ski_area_id,
                lap__activity__start_time__lt=earliest_timestamp
            ).values_list('aerialway', flat=True).distinct()

            previous_lifts_set = set(previous_lifts)
            previous_lifts_by_ski_area[ski_area_id] = previous_lifts_set
            # Cache for 30 minutes
            cache.set(cache_key, previous_lifts_set, 1800)

    # Calculate completeness for each activity
    results = {}
    for activity in activities:
        activity_id = str(activity.id)

        if not activity.ski_area:
            results[activity_id] = {
                'lifts_used_today': 0,
                'total_lifts_available': 0,
                'daily_completion_percentage': 0,
                'new_lifts_discovered': 0
            }
            continue

        try:
            # Get pre-calculated data
            available_lift_ids = ski_area_lifts_cache.get(activity.ski_area.id, set())
            activity_lift_ids = activity_lifts.get(activity.id, set())
            previous_lift_ids = previous_lifts_by_ski_area.get(activity.ski_area.id, set())

            total_available = len(available_lift_ids)
            lifts_used_today = len(activity_lift_ids)

            # Calculate daily completion percentage
            daily_percentage = 0
            if total_available > 0:
                daily_percentage = round((lifts_used_today / total_available) * 100, 1)

            # Calculate new lifts discovered
            new_lifts = activity_lift_ids - previous_lift_ids

            results[activity_id] = {
                'lifts_used_today': lifts_used_today,
                'total_lifts_available': total_available,
                'daily_completion_percentage': daily_percentage,
                'new_lifts_discovered': len(new_lifts)
            }

        except Exception as e:
            logger.error(f"Error calculating completeness for activity {activity.id}: {e}")
            results[activity_id] = {
                'error': 'Error calculating completeness',
                'daily_completion_percentage': 0,
                'lifts_used_today': 0,
                'total_lifts_available': 0,
                'new_lifts_discovered': 0
            }

    return results


def get_lift_statistics(user, ski_area=None):
    """
    Get comprehensive lift ride statistics for a user.

    Returns:
        dict: Detailed lift statistics
    """
    # Base queryset
    rides = LiftRide.objects.filter(lap__activity__user=user)

    if ski_area:
        rides = rides.filter(lap__activity__ski_area=ski_area)

    # Most ridden lift
    most_ridden_lift = rides.values('aerialway__name', 'aerialway__id').annotate(
        ride_count=Count('id')
    ).order_by('-ride_count').first()

    # Recent lift rides
    recent_rides = rides.select_related(
        'aerialway', 'lap__activity__ski_area'
    ).order_by('-timestamp')[:20]

    # Lift type distribution
    lift_types = rides.values('aerialway__aerialway').annotate(
        count=Count('id')
    ).order_by('-count')

    # Unique lifts count
    unique_lifts = rides.values('aerialway').distinct().count()

    # Total rides
    total_rides = rides.count()

    return {
        'most_ridden_lift': most_ridden_lift,
        'recent_rides': recent_rides,
        'lift_types': lift_types,
        'unique_lifts': unique_lifts,
        'total_rides': total_rides
    }


def clear_completeness_cache(user_id, ski_area_id=None, season=None):
    """Clear completeness cache for a user."""
    cache.delete(f"overall_completeness_{user_id}")

    if ski_area_id:
        if season:
            cache.delete(f"completeness_{user_id}_{ski_area_id}_{season}")
        else:
            # Clear all season-specific caches for this ski area
            # Note: This is a simplified approach. In production, consider cache versioning
            cache.delete(f"completeness_{user_id}_{ski_area_id}")
    else:
        # Clear all ski area caches for this user (less efficient but comprehensive)
        # In production, you might want to use cache versioning instead
        pass