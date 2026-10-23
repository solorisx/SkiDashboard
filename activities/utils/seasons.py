from datetime import datetime, timedelta

from django.utils import timezone


def get_seasons(user):
    """Get available seasons for a user based on their activities."""
    from activities.models import Activity

    # Only fetch start_time and user profile data - avoid loading geometry fields
    activities = (
        Activity.objects.filter(user=user)
        .select_related("user", "user__userprofile")
        .only("start_time", "user__userprofile__season_start_month", "user__userprofile__season_start_day")
    )
    seasons = get_seasons_from_activities(activities)
    seasons = [f"{a}-{b}" for (a, b) in seasons]
    seasons.sort(reverse=True)
    return seasons


def _season_start_month_day(user=None):
    """Month and day the ski season starts, from the user's profile or the 1 July default."""
    profile = getattr(user, "userprofile", None) if user else None
    if profile is not None:
        try:
            start = profile.get_season_start_date(2000)  # Year doesn't matter here
            return start.month, start.day
        except AttributeError:
            pass
    return 7, 1


def get_season_dates_containing(day, user=None):
    """Start and end of the season containing ``day``.

    The end is the last moment before the next season starts, so activities on the season's
    final day are included when filtering with ``timestamp__lte=end``.
    """
    start_month, start_day = _season_start_month_day(user)
    start_year = day.year if (day.month, day.day) >= (start_month, start_day) else day.year - 1
    season_start = datetime(start_year, start_month, start_day)
    season_end = datetime(start_year + 1, start_month, start_day) - timedelta(microseconds=1)
    return season_start, season_end


def get_season_dates(current=True, user=None):
    """Get start and end dates for current or previous season.

    Args:
        current: If True, get current season dates, otherwise previous season
        user: Optional user object to use custom season boundaries
    """
    season_start, season_end = get_season_dates_containing(timezone.localdate(), user)
    if current:
        return season_start, season_end
    return get_season_dates_containing(season_start.date() - timedelta(days=1), user)


def parse_season_string(season, user=None):
    """Parse season string (e.g., '2023-2024') into start and end dates."""
    if not season:
        return None, None

    try:
        year1, year2 = map(int, season.split("-"))
    except ValueError:
        raise ValueError("Invalid season format. Use 'YYYY-YYYY'.")

    if year1 >= year2:
        year1, year2 = year2, year1

    # Use user's custom season boundaries or defaults
    if user and hasattr(user, "userprofile"):
        try:
            start_month = user.userprofile.season_start_month
            start_day = user.userprofile.season_start_day
            end_month = user.userprofile.season_end_month
            end_day = user.userprofile.season_end_day
        except AttributeError:
            start_month, start_day = 7, 1
            end_month, end_day = 6, 30
    else:
        start_month, start_day = 7, 1
        end_month, end_day = 6, 30

    start_date = datetime(year1, start_month, start_day)
    end_date = datetime(year2, end_month, end_day)

    return start_date, end_date


def get_season_for_activity(activity):
    """
    Determine which ski season an activity belongs to based on user's season preferences.
    Returns a tuple of (season_start_year, season_end_year).
    For example, an activity on 2023-12-25 might return (2023, 2024) if season starts July 1.
    """
    activity_date = activity.start_time.date()
    user = activity.user

    # Get season boundaries from user preferences or defaults
    if user and hasattr(user, "userprofile"):
        try:
            start_date = user.userprofile.get_season_start_date(2000)  # Year doesn't matter here
            end_date = user.userprofile.get_season_end_date(2000)
            start_month = start_date.month
            start_day = start_date.day
            end_month = end_date.month
            end_day = end_date.day
        except AttributeError:
            start_month, start_day = 7, 1
            end_month, end_day = 6, 30
    else:
        start_month, start_day = 7, 1
        end_month, end_day = 6, 30

    # Check which season the activity falls into
    # Try current year's season first
    season_start_current = datetime(activity_date.year, start_month, start_day).date()
    season_end_current = datetime(activity_date.year + 1, end_month, end_day).date()

    if season_start_current <= activity_date <= season_end_current:
        return (activity_date.year, activity_date.year + 1)

    # Otherwise it's in the previous year's season
    return (activity_date.year - 1, activity_date.year)


def get_seasons_from_activities(activities):
    """Extract unique seasons from a queryset of activities."""
    seasons = set()
    for activity in activities:
        season = get_season_for_activity(activity)
        seasons.add(season)
    return sorted(seasons)
