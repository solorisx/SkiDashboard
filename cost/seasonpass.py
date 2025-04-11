from .models import SeasonPass
from osm.models import SkiArea
from datetime import date
from django.contrib.auth.models import User

def has_seasonpass(user: User, skiarea: SkiArea, date: date):
    return SeasonPass.objects.filter(user=user, skiarea=skiarea, valid_from__lte=date, valid_until__gte=date).exists()