from django.contrib.gis.db import models

# Basic OSM Node Model
class Node(models.Model):
    osm_id = models.BigIntegerField(unique=True)
    geom = models.PointField(srid=4326)
    tags = models.JSONField(default=dict)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Node {self.osm_id}"

# Basic OSM Way Model
class Way(models.Model):
    osm_id = models.BigIntegerField(unique=True)
    nodes = models.ManyToManyField(Node)
    tags = models.JSONField(default=dict)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Way {self.osm_id}"
    
# Station Model
class Station(models.Model):
    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name="station")
    name = models.CharField(max_length=255, blank=True, null=True)
    station = models.CharField(max_length=255, blank=True, null=True)
    altitude = models.FloatField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Station {self.name or self.node.id}"    

# Aerialway Model
class Aerialway(models.Model):
    way = models.OneToOneField(Way, on_delete=models.CASCADE, null=True)
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

# Piste Model
class Piste(models.Model):
    way = models.OneToOneField(Way, on_delete=models.CASCADE)
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

# SkiArea Model
class SkiArea(models.Model):
    osm_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255)
    ways = models.ManyToManyField(Way, related_name='ski_areas')
    url = models.URLField(blank=True, null=True)
    wikipedia = models.CharField(max_length=255, blank=True, null=True)
    tags = models.JSONField(default=dict)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ski Area {self.name}"
