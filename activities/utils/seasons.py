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
    
    if years:
        if not activities.filter(timestamp__lte=datetime(years[-1], 6, 30)):
            years.pop(len(years)-1)
    
    seasons = [f"{y-1}-{y}" for y in years]
    return seasons


def get_season_dates(current=True):
    """Get start and end dates for current or previous season."""
    now = datetime.now()
    
    if current:
        season_start = datetime(now.year, 7, 1) if now.month >= 7 else datetime(now.year-1, 7, 1)
        season_end = datetime(now.year+1, 6, 30) if now.month >= 7 else datetime(now.year, 6, 30)
    else:
        season_start = datetime(now.year-1, 7, 1) if now.month >= 7 else datetime(now.year-2, 7, 1)
        season_end = datetime(now.year, 6, 30) if now.month >= 7 else datetime(now.year-1, 6, 30)
    
    return season_start, season_end


def parse_season_string(season):
    """Parse season string (e.g., '2023-2024') into start and end dates."""
    if not season:
        return None, None
    
    try:
        year1, year2 = map(int, season.split("-"))
    except ValueError:
        raise ValueError("Invalid season format. Use 'YYYY-YYYY'.")
    
    if year1 >= year2:
        year1, year2 = year2, year1
    
    start_date = datetime(year1, 7, 1)
    end_date = datetime(year2, 6, 30)
    
    return start_date, end_date