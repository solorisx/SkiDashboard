from django.contrib import admin
from .models import Node, Way, Station, Aerialway, Piste, SkiArea, SkiAreaNetwork, SkiAreaNetworkMember

admin.site.register(Node)
admin.site.register(Way)
admin.site.register(Station)
admin.site.register(Aerialway)
admin.site.register(Piste)
admin.site.register(SkiArea)
admin.site.register(SkiAreaNetwork)
admin.site.register(SkiAreaNetworkMember)
