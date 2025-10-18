from datetime import datetime
from django.db.models import Q
from django.http import HttpResponse


def get_seasons(user):
    """Get available seasons for a user based on their activities."""
    from activities.models import Activity

    activities = Activity.objects.filter(user=user)
    seasons = get_seasons_from_activities(activities)
    seasons = [f"{a}-{b}" for (a, b) in seasons]
    return seasons


def get_season_dates(current=True, user=None):
    """Get start and end dates for current or previous season.

    Args:
        current: If True, get current season dates, otherwise previous season
        user: Optional user object to use custom season boundaries
    """
    now = datetime.now()

    # Get season boundaries from user preferences or defaults
    if user and hasattr(user, 'userprofile'):
        try:
            start_date = user.userprofile.get_season_start_date(2000) # Year doesn't matter here
            end_date = user.userprofile.get_season_end_date(2000)
            start_month = start_date.month
            start_day = start_date.day
            end_month = end_date.month
            end_day = end_date.day
        except AttributeError:
            # UserProfile doesn't exist, use defaults
            start_month, start_day = 7, 1
            end_month, end_day = 6, 30
    else:
        # Use defaults for anonymous/no-profile users
        start_month, start_day = 7, 1
        end_month, end_day = 6, 30

    if current:
        season_start = datetime(now.year, start_month, start_day) if now.month >= start_month else datetime(now.year-1, start_month, start_day)
        season_end = datetime(now.year+1, end_month, end_day) if now.month >= start_month else datetime(now.year, end_month, end_day)
    else:
        season_start = datetime(now.year-1, start_month, start_day) if now.month >= start_month else datetime(now.year-2, start_month, start_day)
        season_end = datetime(now.year, end_month, end_day) if now.month >= start_month else datetime(now.year-1, end_month, end_day)

    return season_start, season_end


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
    if user and hasattr(user, 'userprofile'):
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
    if user and hasattr(user, 'userprofile'):
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