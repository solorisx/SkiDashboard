from datetime import datetime
from django.db.models import Q
from django.http import HttpResponse


def get_seasons(user):
    """Get available seasons for a user based on their activities."""
    from activities.models import Activity

    activities = Activity.objects.filter(user=user)
    years = set(activities.dates("timestamp", "year", order="DESC"))
    years = [y.year for y in years]
    years.sort(reverse=True)

    # Use user's custom season end date or default to June 30
    if user and hasattr(user, 'userprofile'):
        try:
            end_date = user.userprofile.get_season_end_date(2000) # Year doesn't matter here
            end_month = end_date.month
            end_day = end_date.day
        except AttributeError:
            end_month, end_day = 6, 30
    else:
        end_month, end_day = 6, 30

    if years:
        if not activities.filter(timestamp__lte=datetime(years[-1], end_month, end_day)):
            years.pop(len(years)-1)

    seasons = [f"{y-1}-{y}" for y in years]
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