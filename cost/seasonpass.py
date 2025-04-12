from .models import SeasonPass
from osm.models import SkiArea, SkiAreaNetwork
from datetime import date
from django.contrib.auth.models import User

def has_seasonpass(user: User, skiarea: SkiArea, date: date):
    """
    Check if the user has a valid season pass for the given ski area on the specified date.
    """
    
    for network in SkiAreaNetwork.objects.filter(members__member=skiarea).distinct():
        if SeasonPass.objects.filter(user=user, skiarea_network=network, valid_from__lte=date, valid_until__gte=date).exists():
            return True

    return SeasonPass.objects.filter(user=user, skiarea=skiarea, valid_from__lte=date, valid_until__gte=date).exists()