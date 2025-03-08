from django.db import models
from django.contrib.gis.geos import LineString
from django.contrib.gis.db import models
from djmoney.models.fields import MoneyField
from django.contrib.gis.geos.error import GEOSException
from datetime import datetime
import logging

logger = logging.getLogger('core')

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
    nodes = models.ManyToManyField(Node, through='WayNode', related_name='ways')
    tags = models.JSONField(default=dict)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Way {self.osm_id}"
    
    def get_osm_url(self):
        return f"https://www.openstreetmap.org/way/{self.osm_id}"


class WayNode(models.Model):
    way = models.ForeignKey(Way, on_delete=models.CASCADE)
    node = models.ForeignKey(Node, on_delete=models.CASCADE)
    sequence = models.IntegerField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('way', 'node', 'sequence')
        ordering = ['sequence']

    def __str__(self):
        return f"WayNode {self.way.osm_id} - {self.node.osm_id} - {self.sequence}"


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
    geom_updated_on = models.DateTimeField(null=True, blank=True)
    lit = models.BooleanField(default=False)
    name = models.CharField(max_length=255, blank=True, null=True)
    oneway = models.BooleanField(default=True)
    piste_difficulty = models.CharField(max_length=255, blank=True, null=True)
    piste_grooming = models.CharField(max_length=255, blank=True, null=True)
    piste_type = models.CharField(max_length=255, blank=True, null=True)
    ref = models.CharField(max_length=255, blank=True, null=True)
    segments_generated = models.BooleanField(default=False)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def is_geom_outdated(self):
        """
        Checks if the geometry is outdated based on the last node update.

        This method compares the modification date of the most recently updated node
        associated with the way to the date when the geometry was last updated.

        Returns:
            bool: True if the last node update is more recent than the geometry update, False otherwise.
        """
        last_node_update = self.way.nodes.all().order_by('-modified_on').first().modified_on
        if not last_node_update:
            return False
        return last_node_update > self.geom_updated_on
    
    def update_geometry(self):
        """
        Updates the geometry of the way by creating a LineString from the ordered nodes.

        This method retrieves all nodes associated with the way, orders them by their sequence,
        and constructs a LineString geometry from these nodes. The geometry is then saved to the
        instance along with the current timestamp.

        Returns:
            LineString: The updated geometry if nodes are present.
            None: If no nodes are associated with the way.
        """
        nodes = self.way.nodes.all().order_by('waynode__sequence')
        if len(nodes) > 1:
            self.geom = LineString(*[node.geom for node in nodes])
            self.geom_updated_on = datetime.now()
            self.save()
            return self.geom
        return None


    def generate_segments(self, regenerate=False):
        if regenerate:
            # Remove only the association, don't delete shared segments
            self.segments.clear()

        segments = []
        way_geom = self.geom

        if not way_geom:
            logger.debug(f"No geometry for piste {self.id}")
            way_geom = self.update_geometry()
            if not way_geom:
                logger.warning(f"Could not generate geometry for piste {self.id} - skipping")
                return segments

        if way_geom.geom_type == "LineString":
            segment_lines = [LineString(way_geom.coords[i], way_geom.coords[i + 1])
                            for i in range(len(way_geom.coords) - 1)]
        elif way_geom.geom_type == "MultiLineString":
            segment_lines = [
                LineString(line.coords[i], line.coords[i + 1])
                for line in way_geom
                for i in range(len(line.coords) - 1)
            ]
        else:
            logger.warning(f"Unsupported geometry type {way_geom.geom_type} for piste {self.id}")
            return segments

        for segment_geom in segment_lines:
            buffered_geom = segment_geom.buffer(width=10 / 40000000 * 360, quadsegs=1)  # Buffer to avoid topology exceptions
            existing_segment = PisteSegment.objects.filter(geom__coveredby=buffered_geom).first()

            if existing_segment:
                self.segments.add(existing_segment)
                logger.debug(f"Reused existing segment for piste {self.id}")
            else:
                segment = PisteSegment.objects.create(geom=segment_geom)
                self.segments.add(segment)
                segments.append(segment)
                logger.debug(f"Created new segment for piste {self.id}")

        logger.debug(f"Generated {len(segments)} new segments for piste {self.id}")
        return segments


    def __str__(self):
        return f"Piste {self.way.osm_id} - {self.name}"

    def get_osm_url(self):
        return self.way.get_osm_url()
    

class PisteSegment(models.Model):
    piste = models.ManyToManyField(Piste, related_name='segments')
    geom = models.LineStringField(null=True, blank=True)
    length = models.FloatField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Piste Segment {self.id}"
    
    def save(self, *args, **kwargs):
        if self.geom:
            try:
                metric_geom = self.geom.transform(3857, clone=True)
                self.length = metric_geom.length  # Get length in meters
            except GEOSException:
                self.length = None  # Handle invalid geometries
        super().save(*args, **kwargs)


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
        return f"{self.name}"
    
    def get_osm_url(self):
        if self.way:
            return f"https://www.openstreetmap.org/way/{self.osm_id}"
        else:
            return f"https://www.openstreetmap.org/relation/{self.osm_id}"
    

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
    ski_area_network = models.ForeignKey(SkiAreaNetwork, on_delete=models.CASCADE, related_name='members')
    member = models.ForeignKey(SkiArea, on_delete=models.CASCADE)
    valid_from = models.DateField(null=True)
    valid_to = models.DateField(null=True)
    max_days = models.PositiveIntegerField(default=365)
    valid_during = models.CharField(max_length=10, choices=ValidDuring.choices, default=ValidDuring.all)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ski_area_network.name} - {self.member.name} ({self.valid_from} - {self.valid_to})"
    
    class Meta:
        unique_together = ('ski_area_network', 'member')
