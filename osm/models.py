from django.db import connection, models
from django.contrib.gis.geos import LineString, Point, Polygon
from django.contrib.gis.db import models
from djmoney.models.fields import MoneyField
from django_countries.fields import CountryField
from django.contrib.gis.geos.error import GEOSException
from datetime import datetime
import logging
from .osm_interface import get_osm_data, load_osm_data, get_country_code
from django.utils.functional import cached_property
from django.contrib.gis.db.models.functions import Transform

logger = logging.getLogger(__name__)


class LiftFilterConfig:
    """Configuration for filtering lift types globally and per-user."""

    # Global exclusions - ALWAYS excluded regardless of user settings
    # These are typically data errors or non-ski infrastructure
    GLOBAL_EXCLUDED_LIFT_TYPES = {
        'explosive',        # Explosive lifts (not ski lifts)
        'station',          # Station (not a lift)
        'goods',            # Goods lift (not for passengers)
        'zip_line',         # Zip line (not a ski lift)
        'construction',     # Construction lift (not for skiing)
        'yes',              # data error
        'proposed',         # proposed lift (not existing)
        'planned',          # planned lift (not existing)
        'disused',          # disused lift (not existing)
        'abandoned',        # abandoned lift (not existing)
        'no',               # data error
        'wire_cable',       # wire cable (not a ski lift)
        #'unknown',          # unknown type
        'razed',            # razed lift (not existing)
    }

    # Default user exclusions - can be overridden by user preferences
    # These are often excluded but users might want to include them
    DEFAULT_EXCLUDED_LIFT_TYPES = {
        'magic_carpet',     # Magic carpet (conveyor belt)
        'rope_tow',         # Rope tow (often very short)
    }

    @classmethod
    def get_excluded_lift_types(cls, user=None):
        """Get combined exclusion list for user."""
        excluded = cls.GLOBAL_EXCLUDED_LIFT_TYPES.copy()

        if user and hasattr(user, 'userprofile'):
            # Add user's custom exclusions
            try:
                user_excluded = user.userprofile.excluded_lift_types or []
                excluded.update(user_excluded)
            except AttributeError:
                # UserProfile doesn't exist, use defaults
                excluded.update(cls.DEFAULT_EXCLUDED_LIFT_TYPES)
        else:
            # Use defaults for anonymous/no-profile users
            excluded.update(cls.DEFAULT_EXCLUDED_LIFT_TYPES)

        return excluded

    @classmethod
    def should_include_lift(cls, aerialway_type, user=None):
        """Check if a lift type should be included in calculations."""
        if not aerialway_type:
            return True  # Include lifts with unknown type
        excluded_types = cls.get_excluded_lift_types(user)
        return aerialway_type not in excluded_types

    @classmethod
    def filter_lifts_queryset(cls, queryset, user=None):
        """Filter a queryset of Aerialway objects to exclude configured lift types."""
        excluded_types = cls.get_excluded_lift_types(user)
        return queryset.exclude(aerialway__in=excluded_types)

    # Backward compatibility - use global + default exclusions
    EXCLUDED_LIFT_TYPES = GLOBAL_EXCLUDED_LIFT_TYPES | DEFAULT_EXCLUDED_LIFT_TYPES

    @classmethod
    def get_popular_lift_types(cls, min_count=50):
        """Get aerialway types that occur at least min_count times in the database.

        Excludes GLOBAL_EXCLUDED_LIFT_TYPES as these should never be user-configurable.
        Returns a list of tuples (aerialway_type, count) for use in forms.
        """
        from django.db.models import Count

        popular_types = (
            Aerialway.objects
            .exclude(aerialway__in=cls.GLOBAL_EXCLUDED_LIFT_TYPES)
            .values('aerialway')
            .annotate(count=Count('id'))
            .filter(count__gte=min_count)
            .order_by('-count', 'aerialway')
        )

        return [(item['aerialway'], f"{item['aerialway'].replace('_', ' ').title()}")
                for item in popular_types]


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

    @cached_property
    def constructed_geom(self):
        """
        Construct geometry from way nodes.
        Returns LineString for open ways or Polygon for closed ways.
        Result is cached until the way is modified.
        """
        try:
            # Get nodes in order
            way_nodes = self.nodes.all().order_by('waynode__sequence')

            if way_nodes.count() < 2:
                logger.warning(f"Way {self.osm_id} has insufficient nodes ({way_nodes.count()})")
                return None

            # Extract coordinates from node geometries
            coords = []
            for node in way_nodes:
                if node.geom:
                    coords.append((node.geom.x, node.geom.y))

            if len(coords) < 2:
                logger.warning(f"Way {self.osm_id} has insufficient valid coordinates ({len(coords)})")
                return None

            # Determine if way is closed (first and last nodes are the same)
            is_closed = len(coords) >= 3 and coords[0] == coords[-1]

            # For closed ways with 3+ coordinates, create a Polygon
            if is_closed and len(coords) >= 4:  # Need at least 4 points for valid polygon (including closure)
                return Polygon(coords)

            # For open ways or insufficient points for polygon, create LineString
            return LineString(coords)

        except Exception as e:
            logger.error(f"Error constructing geometry for way {self.osm_id}: {e}")
            return None


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
    
    @cached_property
    def get_location(self):
        skiarea = self.way.ski_areas.first()
        if not skiarea:
            ski_areas = SkiArea.objects.filter(geom__isnull=False)
            geom = self.way.constructed_geom
            try:
                skiarea = (
                    ski_areas
                    .filter(geom__intersects=geom)
                    .first()
                )
            except Exception as e:
                skiarea = None
                logger.warning(f"Exception when checking if point is within ski area for aerialway {self.way.osm_id}: {e}")
                raise e
        return skiarea

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
    country = CountryField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name}"
    
    def set_country(self, country=None):
        if self.way:
            country_code = get_country_code(self.way.osm_id, "Way")
        else:
            country_code = get_country_code(self.osm_id, "Relation")
        if country_code:
            self.country = country_code
            self.save()
    

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
    
    def list_members_array(self, valid_from=None, valid_to=None):
        if valid_from and valid_to:
            members = self.members.filter(
                models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=valid_to),
                models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=valid_from)
            )
        elif valid_from:
            members = self.members.filter(
                models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=valid_from)
            )
        elif valid_to:
            members = self.members.filter(
                models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=valid_to)
            )
        else:
            members = self.members.all()
        return members
    
    def list_members(self, valid_from=None, valid_to=None):
        members = self.list_members_array(valid_from, valid_to)
        names = []
        for member in members:
            name_str = f"{member.member.name}"
            if member.max_days and member.max_days < 365:
                name_str += f" (max {member.max_days} days)"
            names.append(name_str)
        unique_names = list(set(names))  # Remove duplicates
        return ", ".join(unique_names)
    
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
