from .models import TicketPrice
from osm.models import SkiArea
from datetime import date
from django.contrib.auth.models import User
from djmoney.money import Money
import geopandas as gpd
import logging

logger = logging.getLogger('core')


WORLD_SHAPEFILE_PATH = "osm/world/ne_110m_admin_0_countries.shp"
world = gpd.read_file(WORLD_SHAPEFILE_PATH).to_crs(epsg=4326)  # Ensure it matches SkiArea's CRS

def get_fallback_daypass_price(skiarea: SkiArea, date: date):
    """
    Determines a fallback day pass price based on the ski area's location within a country shapefile.
    """
    
    if not skiarea.country:
        skiarea.set_country()
    
    if skiarea.country:
        # Check if the ski area has a country set
        country_name = skiarea.country.name

        # Assign fallback prices based on country
        if country_name == 'Switzerland':
            return Money(75, 'CHF')
        elif country_name in ('Austria', 'Germany', 'Italy', 'France'):
            return Money(60, 'EUR')
        elif country_name == 'United States':
            return Money(100, 'USD')
        elif country_name == 'Canada':
            return Money(100, 'CAD')
        return None

    return None  # No country match

def get_daypass_price(skiarea: SkiArea, date: date, user: User = None):
    """
    Determines the best day pass price for a given ski area and date.
    Tries user-specific prices, then general prices, and finally falls back to country-based pricing.
    """
    price = None

    # Check user-specific price first
    if user:
        price = TicketPrice.objects.filter(
            skiarea=skiarea, valid_from__lte=date, valid_until__gte=date, user=user
        ).first()

    # Check general price if user-specific price is missing
    if not price:
        price = TicketPrice.objects.filter(
            skiarea=skiarea, valid_from__lte=date, valid_until__gte=date, user=None
        ).first()

    # Use fallback price if no ticket prices are found
    if not price:
        price = get_fallback_daypass_price(skiarea, date)

    # Default to CHF 75 if all else fails
    if not price:
        price = Money(75, 'CHF')

    return price
