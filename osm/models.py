from django.db import models
from django.contrib.gis.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from djmoney.models.fields import MoneyField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType



class ValidDuring(models.TextChoices):
    winter = 'winter', 'Winter'
    summer = 'summer', 'Summer'
    all = 'all', 'All Seasons'


# Basic OSM Node Model
class Node(models.Model):
    osm_id = models.BigIntegerField(unique=True)
    geom = models.PointField(srid=4326)
    tags = models.JSONField(default=dict)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Node {self.osm_id}"
    
    def get_osm_url(self):
        return f"https://www.openstreetmap.org/node/{self.osm_id}"

# Basic OSM Way Model
class Way(models.Model):
    osm_id = models.BigIntegerField(unique=True)
    nodes = models.ManyToManyField(Node)
    tags = models.JSONField(default=dict)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Way {self.osm_id}"
    
    def get_osm_url(self):
        return f"https://www.openstreetmap.org/way/{self.osm_id}"
    
# Station Model
class Station(models.Model):
    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name="station")
    name = models.CharField(max_length=255, blank=True, null=True)
    station = models.CharField(max_length=255, blank=True, null=True)
    altitude = models.FloatField(blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Station {self.name or self.node.id}"
    
    def get_osm_url(self):
        return self.node.get_osm_url()

# Aerialway Model
class Aerialway(models.Model):
    way = models.OneToOneField(Way, on_delete=models.CASCADE, null=True)
    geom = models.LineStringField(null=True, blank=True)
    aerialway = models.CharField(max_length=255)
    aerialway_bubble = models.BooleanField(default=False)
    aerialway_capacity = models.IntegerField(blank=True, null=True)
    aerialway_duration = models.IntegerField(blank=True, null=True)
    aerialway_heating = models.BooleanField(default=False)
    aerialway_occupancy = models.IntegerField(blank=True, null=True)
    station_nodes = models.ManyToManyField(Station, related_name="aerialways")
    bottom_station = models.ForeignKey(Station, null=True, on_delete=models.CASCADE, related_name="bottom_aerialways")
    top_station = models.ForeignKey(Station, null=True, on_delete=models.CASCADE, related_name="top_aerialways")
    name = models.CharField(max_length=255, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Aerialway {self.way.osm_id} - {self.name}"
    
    def get_osm_url(self):
        return self.way.get_osm_url()

# Piste Model
class Piste(models.Model):
    way = models.OneToOneField(Way, on_delete=models.CASCADE)
    geom = models.LineStringField(null=True, blank=True)
    lit = models.BooleanField(default=False)
    name = models.CharField(max_length=255, blank=True, null=True)
    oneway = models.BooleanField(default=True)
    piste_difficulty = models.CharField(max_length=255, blank=True, null=True)
    piste_grooming = models.CharField(max_length=255, blank=True, null=True)
    piste_type = models.CharField(max_length=255, blank=True, null=True)
    ref = models.CharField(max_length=255, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Piste {self.way.osm_id} - {self.name}"

    def get_osm_url(self):
        return self.way.get_osm_url()
    
class PisteSegment(models.Model):
    piste = models.ForeignKey(Piste, on_delete=models.CASCADE, related_name='segments')
    geom = models.LineStringField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Piste Segment {self.piste.way.osm_id} - {self.geom.length}"


class AbstractSkiArea(models.Model):
    name = models.CharField(max_length=255, null=True)
    geom = models.MultiPolygonField(null=True, blank=True)

    daypass_price = MoneyField(max_digits=6, decimal_places=2, blank=True, null=True, default_currency='CHF')
    seasonpass_price = MoneyField(max_digits=6, decimal_places=2, blank=True, null=True, default_currency='CHF')
    
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"Ski Area {self.name}"
    
    def get_osm_id(self):
        if hasattr(self, 'osm_id'):
            return self.osm_id
        elif hasattr(self, 'way'):
            return self.way.osm_id
        else:
            return None
    
    def get_osm_url(self):
        return f"https://www.openstreetmap.org/relation/{self.osm_id}"   
    

# SkiArea Model
class SkiArea(AbstractSkiArea):
    osm_id = models.BigIntegerField(unique=True) # osm_id of relation or of boundary way of area
    osm_type = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, null=True)
    geom = models.MultiPolygonField(null=True, blank=True)
    ways = models.ManyToManyField(Way, related_name='ski_areas')
    way = models.OneToOneField(Way, on_delete=models.CASCADE, related_name="boundary", null=True)
    url = models.URLField(blank=True, null=True)
    wikipedia = models.CharField(max_length=255, blank=True, null=True)
    tags = models.JSONField(default=dict)
    daypass_price = MoneyField(max_digits=6, decimal_places=2, blank=True, null=True, default_currency='CHF')
    seasonpass_price = MoneyField(max_digits=6, decimal_places=2, blank=True, null=True, default_currency='CHF')
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ski Area {self.name}"
    
    def get_osm_url(self):
        if self.osm_id:
            return f"https://www.openstreetmap.org/relation/{self.osm_id}"
        else:
            return self.way.get_osm_url()
    

class SkiAreaBoundary(AbstractSkiArea):
    way = models.OneToOneField(Way, on_delete=models.CASCADE, related_name="ski_area_boundary")  # Added explicit related_name
    ways = models.ManyToManyField(Way, related_name='ski_area_boundaries')

    def __str__(self):
        return f"Ski Area Boundary {self.way.osm_id}"
    
    def get_osm_url(self):
        return self.way.get_osm_url()


class SkiAreaNetwork(models.Model):
    name = models.CharField(max_length=255, unique=True)
    season_pass_price = MoneyField(max_digits=10, decimal_places=2, default_currency='CHF', null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ski Area Network {self.name}"
    
class SkiAreaNetworkMember(models.Model):
    ski_area_network = models.ForeignKey(SkiAreaNetwork, on_delete=models.CASCADE)
    member = models.ForeignKey(SkiArea, on_delete=models.CASCADE)
    valid_from = models.DateField(null=True)
    valid_to = models.DateField(null=True)
    max_days = models.PositiveIntegerField(default=365)
    valid_during = models.CharField(max_length=10, choices=ValidDuring.choices, default=ValidDuring.all)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ski_area_network.name} - {self.member.name} ({self.valid_from} - {self.valid_to})"
