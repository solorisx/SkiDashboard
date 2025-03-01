from .models import TicketPrice
from osm.models import SkiArea
from datetime import date


def get_daypass_price(skiarea: SkiArea, date: date):
    return TicketPrice.objects.filter(skiarea=skiarea, type='daypass', valid_from__lte=date, valid_until__gte=date).first().price
