from .models import TicketPrice
from osm.models import SkiArea
from datetime import date
from django.contrib.auth.models import User
from djmoney.models.fields import MoneyField
import geopandas as gpd


def get_fallback_daypass_price(skiarea: SkiArea, date: date):

    if skiarea.geom:
        world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
        country = world[world.contains[skiarea.geom]]

        if country:
            if country.iloc[0]['name'] == 'Switzerland':
                return MoneyField(amount=75, currency='CHF')
            elif country.iloc[0]['name'] in ('Austria', 'Germany', 'Italy', 'France'):
                return MoneyField(amount=60, currency='EUR')
            elif country.iloc[0]['name'] == 'United States':
                return MoneyField(amount=100, currency='USD')
            elif country.iloc[0]['name'] == 'Canada':
                return MoneyField(amount=100, currency='CAD')

    return None

def get_daypass_price(skiarea: SkiArea, date: date, user: User=None):
    price = None
    if user:
        price = TicketPrice.objects.filter(skiarea=skiarea, type='daypass', valid_from__lte=date, valid_until__gte=date, user=user).first()
    if not price:
        price = TicketPrice.objects.filter(skiarea=skiarea, type='daypass', valid_from__lte=date, valid_until__gte=date, user=None).first()
    if not price:
        price = get_fallback_daypass_price(skiarea, date)
    if not price:
        price = MoneyField(amount=75, currency='CHF')
    return price