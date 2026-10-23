import logging

logger = logging.getLogger(__name__)


def generate_trip_name(activities):
    """Generate an automatic trip name based on the activities' ski areas and date range."""
    if not activities:
        return "Ski Trip"

    # Get unique ski area names (preserve encounter order)
    seen = set()
    ski_areas = []
    for a in activities:
        if a.ski_area and a.ski_area.name not in seen:
            seen.add(a.ski_area.name)
            ski_areas.append(a.ski_area.name)

    # Get date range
    dates = [a.timestamp.date() for a in activities]
    start_date = min(dates)
    end_date = max(dates)

    # Format date range
    if start_date == end_date:
        date_str = start_date.strftime("%b %-d, %Y")
    elif start_date.year == end_date.year and start_date.month == end_date.month:
        date_str = f"{start_date.strftime('%b %-d')}-{end_date.strftime('%-d, %Y')}"
    elif start_date.year == end_date.year:
        date_str = f"{start_date.strftime('%b %-d')} – {end_date.strftime('%b %-d, %Y')}"
    else:
        date_str = f"{start_date.strftime('%b %-d, %Y')} – {end_date.strftime('%b %-d, %Y')}"

    if ski_areas:
        if len(ski_areas) == 1:
            location = ski_areas[0]
        elif len(ski_areas) == 2:
            location = f"{ski_areas[0]} & {ski_areas[1]}"
        else:
            location = f"{ski_areas[0]}, {ski_areas[1]} +{len(ski_areas) - 2}"
        return f"{location} – {date_str}"
    else:
        return f"Ski Trip – {date_str}"


def cluster_activities_into_trips(user):
    """
    Cluster a user's activities into trips.

    Two activities belong to the same trip if there is at most one idle day
    between their dates (i.e. the gap between consecutive activity dates is ≤ 2 days).

    Existing trip names modified by the user are preserved when the date range
    of the cluster matches an existing trip exactly.
    """
    from .models import Activity, Trip

    # Fetch all activities ordered oldest-first so we can compute gaps
    activities = list(
        Activity.objects.filter(user=user)
        .select_related('ski_area')
        .order_by('timestamp')
    )

    if not activities:
        # No activities → remove all trips for this user
        Trip.objects.filter(user=user).delete()
        return

    # --- Build clusters ---
    clusters = []          # list of lists of Activity
    current_cluster = [activities[0]]

    for activity in activities[1:]:
        activity_date = activity.timestamp.date()
        last_date = current_cluster[-1].timestamp.date()
        gap = (activity_date - last_date).days

        if gap <= 2:  # same day (0), consecutive (1), or one idle day (2)
            current_cluster.append(activity)
        else:
            clusters.append(current_cluster)
            current_cluster = [activity]

    clusters.append(current_cluster)

    # --- Snapshot existing trips keyed by (start_date, end_date) ---
    existing_trips = {
        (t.start_date, t.end_date): t
        for t in Trip.objects.filter(user=user)
    }

    # --- Match clusters to existing trips and create/update as needed ---
    used_trip_ids = set()

    for cluster in clusters:
        dates = [a.timestamp.date() for a in cluster]
        start_date = min(dates)
        end_date = max(dates)
        key = (start_date, end_date)

        auto_name = generate_trip_name(cluster)

        if key in existing_trips:
            trip = existing_trips[key]
            trip.auto_name = auto_name
            # Only overwrite the display name if the user hasn't changed it
            if not trip.name_modified:
                trip.name = auto_name
            trip.save(update_fields=['auto_name', 'name', 'modified_on'])
        else:
            trip = Trip.objects.create(
                user=user,
                name=auto_name,
                auto_name=auto_name,
                start_date=start_date,
                end_date=end_date,
            )

        used_trip_ids.add(trip.id)

        # Assign activities to this trip
        Activity.objects.filter(pk__in=[a.pk for a in cluster]).update(trip=trip)

    # --- Clear trip from activities that no longer belong to any cluster ---
    # (shouldn't normally happen, but defensive)
    Activity.objects.filter(user=user).exclude(
        pk__in=[a.pk for cluster in clusters for a in cluster]
    ).update(trip=None)

    # --- Delete trips that are no longer referenced ---
    Trip.objects.filter(user=user).exclude(pk__in=used_trip_ids).delete()

    logger.info(
        "Clustered %d activities into %d trips for user %s",
        len(activities),
        len(clusters),
        user.username,
    )
