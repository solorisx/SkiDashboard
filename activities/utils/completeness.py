import logging
from django.core.cache import cache
from django.db.models import Count

from activities.models import LiftRide, PisteRide
from osm.models import Aerialway, SkiArea, LiftFilterConfig, Piste

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

    # Check cache first - data only changes if activity is reprocessed or manually modified
    cache_key = f"activity_completeness_{activity.id}"
    cached_result = cache.get(cache_key)

    if cached_result is not None:
        logger.debug(f"Using cached completeness for activity {activity.id}")
        return cached_result

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

    result = {
        'lifts_used_today': len(activity_lifts),
        'total_lifts_available': total_available,
        'daily_completion_percentage': daily_percentage,
        'new_lifts_discovered': len(new_lifts)
    }

    # Cache indefinitely - only changes if activity is reprocessed or manually modified
    cache.set(cache_key, result, None)
    logger.debug(f"Cached completeness for activity {activity.id}")

    return result


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


# ============================================================================
# PISTE COMPLETENESS FUNCTIONS
# ============================================================================
# The following functions provide distance-based completeness tracking for
# pistes, mirroring the count-based lift completeness logic above.
# ============================================================================


def get_available_pistes_in_ski_area(ski_area, user=None):
    """
    Get all available downhill, line-based pistes in a ski area.

    Args:
        ski_area: SkiArea object
        user: User object (currently unused, reserved for future filtering)

    Returns:
        QuerySet of Piste objects (downhill, line-based only, with cached length)
    """
    # Check cache first
    cache_key = f"available_pistes_{ski_area.id}_{user.id if user else 'anon'}"
    cached_piste_ids = cache.get(cache_key)
    if cached_piste_ids:
        logger.debug(f"Using cached available pistes for ski area {ski_area.id}")
        return Piste.objects.filter(id__in=cached_piste_ids)

    try:
        pistes = Piste.objects.none()
        from django.db.models import Q
        query = Q(piste_type='downhill') & ~Q(piste_difficulty='freeride') & Q(length__gt=100) & ~Q(piste_grooming='backcountry')

        # Strategy 1: Direct geometry intersection
        if ski_area.geom:
            pistes_with_geom = Piste.objects.exclude(geom__isnull=True).exists()
            if pistes_with_geom:
                # Filter for downhill pistes (piste_type='downhill' and not piste_difficulty='freeride'
                pistes = Piste.objects.filter(
                    geom__intersects=ski_area.geom
                ).filter(
                    query
                ).exclude(geom__isnull=True).distinct()
                logger.info(f"Using direct geometry intersection for ski area {ski_area.id}")

        # Strategy 2: Boundary way constructed geometry
        if not pistes.exists() and ski_area.way:
            boundary_geom = ski_area.way.constructed_geom
            if boundary_geom:
                pistes = Piste.objects.filter(
                    geom__intersects=boundary_geom
                ).filter(
                    query
                ).exclude(geom__isnull=True).distinct()
                logger.info(f"Using constructed geometry for ski area {ski_area.id}")

        # Strategy 3: Way relationships fallback
        if not pistes.exists():
            pistes = Piste.objects.filter(
                way__ski_areas=ski_area
            ).filter(
                query
            ).exclude(geom__isnull=True).distinct()
            if pistes.exists():
                logger.info(f"Found {pistes.count()} pistes using way relationships for ski area {ski_area.id}")

        # Strategy 4: Check duplicate ski areas
        if not pistes.exists():
            duplicate_areas = SkiArea.objects.filter(name=ski_area.name).exclude(id=ski_area.id)
            for dup in duplicate_areas:
                if dup.geom:
                    pistes = Piste.objects.filter(
                        geom__intersects=dup.geom
                                ).filter(
                                    query
                    ).exclude(geom__isnull=True).distinct()
                elif dup.way:
                    pistes = Piste.objects.filter(
                        way__ski_areas=dup
                    ).filter(
                        query
                    ).exclude(geom__isnull=True).distinct()
                if pistes.exists():
                    logger.info(f"Found pistes using duplicate ski area {dup.id}")
                    break

        # Strategy 5: Actual ride data fallback
        if not pistes.exists():
            ridden_piste_ids = PisteRide.objects.filter(
                lap__activity__ski_area=ski_area
            ).values_list('piste', flat=True).distinct()

            if ridden_piste_ids:
                pistes = Piste.objects.filter(
                    id__in=ridden_piste_ids
                ).filter(
                    query
                ).exclude(geom__isnull=True)
                logger.info(f"Found {pistes.count()} pistes using ride data for ski area {ski_area.id}")

        # CRITICAL: Post-filter for line-based pistes only
        # Since is_area() is a Python method, we must do this in-memory
        line_piste_ids = []
        for piste in pistes:
            if not piste.is_area():
                line_piste_ids.append(piste.id)

        logger.info(f"Found {len(line_piste_ids)} line-based pistes for ski area {ski_area.id}")

        # Cache the result for 30 minutes
        cache.set(cache_key, line_piste_ids, 1800)

        return Piste.objects.filter(id__in=line_piste_ids)

    except Exception as e:
        logger.warning(f"Error finding pistes in ski area {ski_area.id}: {e}")
        return Piste.objects.none()


def calculate_ski_area_piste_completeness(user, ski_area, force_calc=False, season=None):
    """
    Calculate distance-based piste completeness for a user in a specific ski area.

    Uses distance-based metric: (total_distance_ridden / total_distance_available) × 100

    Args:
        user: User object
        ski_area: SkiArea object
        force_calc: Whether to force recalculation (ignore cache)
        season: Optional season string (e.g., "2023-2024") for season-specific filtering

    Returns:
        dict: {
            'total_distance_available': float (meters),
            'total_distance_ridden': float (meters),
            'completion_percentage': float,
            'pistes_ridden': list of dicts,
            'pistes_not_ridden': list of dicts
        }
    """
    logger.debug(f"Calculating piste completeness for user {user.id} in ski area {ski_area.id}, season={season}")

    # Cache key includes season
    cache_key = f"piste_completeness_{user.id}_{ski_area.id}"
    if season:
        cache_key += f"_{season}"

    if not force_calc:
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.debug("Using cached piste completeness")
            return cached_result

    # Get all available line-based pistes
    available_pistes = get_available_pistes_in_ski_area(ski_area, user=user)

    # Calculate total available distance
    total_distance_available = sum(
        p.length for p in available_pistes if p.length
    )

    if total_distance_available == 0:
        result = {
            'total_distance_available': 0,
            'total_distance_ridden': 0,
            'completion_percentage': 0,
            'pistes_ridden': [],
            'pistes_not_ridden': []
        }
        cache.set(cache_key, result, 3600)  # Cache for 1 hour even if no pistes
        return result

    # Get pistes the user has ridden
    user_piste_rides_query = PisteRide.objects.filter(
        lap__activity__user=user,
        lap__activity__ski_area=ski_area,
        piste__in=available_pistes
    )

    # Apply season filtering
    if season:
        from activities.utils.seasons import parse_season_string
        season_start, season_end = parse_season_string(season, user=user)
        if season_start and season_end:
            user_piste_rides_query = user_piste_rides_query.filter(
                lap__activity__start_time__gte=season_start,
                lap__activity__start_time__lte=season_end
            )

    # Get unique pistes ridden
    ridden_piste_ids = user_piste_rides_query.values_list('piste', flat=True).distinct()
    ridden_pistes = available_pistes.filter(id__in=ridden_piste_ids)
    not_ridden_pistes = available_pistes.exclude(id__in=ridden_piste_ids).order_by('length')

    # Calculate total distance ridden
    total_distance_ridden = sum(
        p.length for p in ridden_pistes if p.length
    )

    completion_percentage = 0
    if total_distance_available > 0:
        completion_percentage = round(
            (total_distance_ridden / total_distance_available) * 100, 1
        )

    # Calculate average distance per piste
    avg_distance_per_piste = 0
    pistes_ridden_list = list(ridden_pistes.values('id', 'name', 'length', 'piste_difficulty'))
    pistes_not_ridden_list = list(not_ridden_pistes.values('id', 'name', 'length', 'piste_difficulty'))

    if pistes_ridden_list:
        avg_distance_per_piste = round(total_distance_ridden / len(pistes_ridden_list), 1)

    result = {
        'total_distance_available': round(total_distance_available, 1),
        'total_distance_ridden': round(total_distance_ridden, 1),
        'completion_percentage': completion_percentage,
        'avg_distance_per_piste': avg_distance_per_piste,
        'total_pistes_available': len(pistes_ridden_list) + len(pistes_not_ridden_list),
        'pistes_ridden': pistes_ridden_list,
        'pistes_not_ridden': pistes_not_ridden_list
    }

    # Cache indefinitely, clear on data change
    cache.set(cache_key, result, None)
    return result


def get_ski_area_total_distance_cached(ski_area, user):
    """
    Get total available piste distance for a ski area with caching.

    Args:
        ski_area: SkiArea object
        user: User object

    Returns:
        float: total_distance_available
    """
    cache_key = f"available_pistes_distance_{ski_area.id}_{user.id}"
    cached_result = cache.get(cache_key)

    if cached_result is not None:
        logger.debug(f"Using cached available pistes distance for ski area {ski_area.id}")
        return cached_result

    available_pistes = get_available_pistes_in_ski_area(ski_area, user=user)
    total_distance_available = sum(p.length for p in available_pistes if p.length)

    # Cache for 1 hour
    cache.set(cache_key, total_distance_available, 3600)

    return total_distance_available


def calculate_activity_piste_completeness(activity):
    """
    Calculate piste completeness for a single activity.

    Args:
        activity: Activity object

    Returns:
        dict: {
            'distance_skied_today': float (meters),
            'total_distance_available': float (meters),
            'daily_completion_percentage': float,
            'new_pistes_discovered': int,
            'new_distance_discovered': float (meters)
        }
    """
    if not activity.ski_area:
        return {
            'distance_skied_today': 0,
            'total_distance_available': 0,
            'daily_completion_percentage': 0,
            'new_pistes_discovered': 0,
            'new_distance_discovered': 0
        }

    # Check cache first - data only changes if activity is reprocessed or manually modified
    cache_key = f"activity_piste_completeness_{activity.id}"
    cached_result = cache.get(cache_key)

    if cached_result is not None:
        logger.debug(f"Using cached piste completeness for activity {activity.id}")
        return cached_result

    # Get pistes ridden in this activity
    activity_piste_rides = PisteRide.objects.filter(
        lap__activity=activity
    ).select_related('piste')

    activity_piste_ids = activity_piste_rides.values_list('piste', flat=True).distinct()
    activity_pistes = Piste.objects.filter(id__in=activity_piste_ids)

    # Calculate distance skied today (only line-based pistes)
    distance_skied_today = sum(
        p.length for p in activity_pistes if p.length and not p.is_area()
    )

    # Get total available piste distance for ski area (cached)
    total_distance_available = get_ski_area_total_distance_cached(
        activity.ski_area, activity.user
    )

    # Calculate daily completion percentage
    daily_percentage = 0
    if total_distance_available > 0:
        daily_percentage = round((distance_skied_today / total_distance_available) * 100, 1)

    # Calculate new pistes discovered (not ridden before this activity)
    previous_piste_rides = PisteRide.objects.filter(
        lap__activity__user=activity.user,
        lap__activity__ski_area=activity.ski_area,
        lap__activity__start_time__lt=activity.start_time
    ).values_list('piste', flat=True).distinct()

    new_piste_ids = set(activity_piste_ids) - set(previous_piste_rides)
    new_pistes = Piste.objects.filter(id__in=new_piste_ids)

    new_distance_discovered = sum(
        p.length for p in new_pistes if p.length and not p.is_area()
    )

    result = {
        'distance_skied_today': round(distance_skied_today, 1),
        'total_distance_available': round(total_distance_available, 1),
        'daily_completion_percentage': daily_percentage,
        'new_pistes_discovered': len(new_piste_ids),
        'new_distance_discovered': round(new_distance_discovered, 1)
    }

    # Cache indefinitely - only changes if activity is reprocessed or manually modified
    cache.set(cache_key, result, None)
    logger.debug(f"Cached piste completeness for activity {activity.id}")

    return result


def calculate_batch_activity_piste_completeness(activities, user):
    """
    Calculate piste completeness for multiple activities by calling the individual function.

    Args:
        activities: List of Activity objects
        user: User object

    Returns:
        dict: Mapping of activity_id to piste completeness data
    """
    results = {}
    for activity in activities:
        completeness = calculate_activity_piste_completeness(activity)
        results[str(activity.id)] = completeness

    return results


def calculate_overall_piste_completeness(user):
    """
    Calculate overall piste completeness across all visited ski areas for a user.

    Args:
        user: User object

    Returns:
        dict: Overall completeness statistics
    """
    cache_key = f"overall_piste_completeness_{user.id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.debug(f"Using cached overall piste completeness for user {user.id}")
        return cached_result

    # Get all ski areas the user has visited
    visited_ski_areas = SkiArea.objects.filter(
        activity__user=user
    ).distinct()

    if not visited_ski_areas.exists():
        result = {
            'total_ski_areas': 0,
            'total_distance_available': 0,
            'total_distance_ridden': 0,
            'overall_percentage': 0,
            'ski_area_breakdown': []
        }
        cache.set(cache_key, result, 3600)
        return result

    ski_area_breakdown = []
    total_distance_available = 0
    total_distance_ridden = 0

    for ski_area in visited_ski_areas:
        completeness = calculate_ski_area_piste_completeness(user, ski_area)
        ski_area_breakdown.append({
            'ski_area_id': ski_area.id,
            'ski_area_name': ski_area.name,
            'completeness': completeness
        })
        total_distance_available += completeness['total_distance_available']
        total_distance_ridden += completeness['total_distance_ridden']

    overall_percentage = 0
    if total_distance_available > 0:
        overall_percentage = round(
            (total_distance_ridden / total_distance_available) * 100, 1
        )

    result = {
        'total_ski_areas': visited_ski_areas.count(),
        'total_distance_available': round(total_distance_available, 1),
        'total_distance_ridden': round(total_distance_ridden, 1),
        'overall_percentage': overall_percentage,
        'ski_area_breakdown': ski_area_breakdown
    }

    cache.set(cache_key, result, 3600)  # 1 hour cache
    return result


def clear_piste_completeness_cache(user_id, ski_area_id=None, season=None):
    """Clear piste completeness cache for a user."""
    cache.delete(f"overall_piste_completeness_{user_id}")

    if ski_area_id:
        cache.delete(f"piste_completeness_{user_id}_{ski_area_id}_{season or ''}")
        cache.delete(f"available_pistes_{ski_area_id}_{user_id}")