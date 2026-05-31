from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from djmoney.models.fields import MoneyField
from osm.models import Aerialway, Piste, SkiArea, SkiAreaBoundary, PisteSegment
from django.core.validators import MinValueValidator, MaxValueValidator


class Trip(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    auto_name = models.CharField(max_length=200, blank=True)
    name_modified = models.BooleanField(default=False, help_text="True if user has manually changed the name")
    start_date = models.DateField()
    end_date = models.DateField()
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['user', '-start_date'], name='trip_user_start_date_idx'),
        ]

    def __str__(self):
        return f"{self.name}"

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def num_activities(self):
        return self.activities.count()


class Activity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    geom = models.LineStringField(null=True)
    summary_polyline = models.TextField(null=True)
    polyline = models.TextField(null=True)
    file_id = models.PositiveBigIntegerField(null=True)
    strava_id = models.PositiveBigIntegerField(null=True, unique=True)
    type = models.CharField(max_length=255, null=True)
    timestamp = models.DateTimeField()
    start_time = models.DateTimeField()
    timezone = models.CharField(max_length=100, null=True, blank=True, help_text="IANA timezone name (e.g., Europe/Zurich)")
    total_elapsed_time = models.DurationField()
    total_timer_time = models.DurationField()
    total_distance = models.FloatField()
    start_position = models.PointField()
    sport_profile_name = models.CharField(max_length=255)
    avg_speed = models.FloatField(null=True)
    max_speed = models.FloatField(null=True)
    total_calories = models.FloatField(null=True)
    total_ascent = models.FloatField(null=True)
    total_descent = models.FloatField(null=True)
    first_lap_index = models.PositiveIntegerField(null=True)
    avg_heart_rate = models.PositiveIntegerField(null=True)
    max_heart_rate = models.PositiveIntegerField(null=True)
    num_laps = models.PositiveIntegerField(null=True)
    num_lift_rides = models.PositiveIntegerField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    processed_on = models.DateTimeField(null=True)
    processing_time = models.DurationField(null=True)
    version = models.PositiveIntegerField(default=1)
    device_name = models.CharField(max_length=255, null=True)
    manually_modified = models.BooleanField(default=False, help_text="True if user has manually added/edited lift rides")
    strava_description_updated = models.BooleanField(default=False, help_text="True if Strava description has been updated with lift rides")

    ski_area = models.ForeignKey(SkiArea, on_delete=models.PROTECT, null=True)
    trip = models.ForeignKey('Trip', on_delete=models.SET_NULL, null=True, blank=True, related_name='activities')

    cost = MoneyField(max_digits=10, decimal_places=2, default_currency='CHF', null=True)
    value = MoneyField(max_digits=10, decimal_places=2, default_currency='CHF', null=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-timestamp'], name='activity_user_timestamp_idx'),
            models.Index(fields=['ski_area', '-timestamp'], name='activity_skiarea_timestamp_idx'),
            models.Index(fields=['user', 'ski_area'], name='activity_user_skiarea_idx'),
        ]

    def __str__(self):
        return f"{self.name}"

    def get_strava_url(self):
        return f"https://www.strava.com/activities/{self.strava_id}" if self.strava_id else None

    def get_num_lift_rides(self):
        return sum(lap.lift_rides.count() for lap in self.laps.all())
    
    def set_num_lift_rides(self):
        self.num_lift_rides = self.get_num_lift_rides()
        self.save()
    
    def has_valid_season_pass(self):
        """Check if this activity is covered by a valid season pass."""
        from cost.models import SeasonPass
        from django.db.models import Q
        
        activity_date = self.timestamp.date()
        
        # Check for season passes that cover this activity's ski area and date
        season_passes = SeasonPass.objects.filter(
            user=self.user,
            valid_from__lte=activity_date,
            valid_until__gte=activity_date
        ).filter(
            Q(skiarea=self.ski_area) |  # Direct ski area match
            Q(skiarea_network__members__member=self.ski_area)  # Ski area network match through members
        )
        
        return season_passes.exists()
    
    def get_valid_season_pass(self):
        """Get the valid season pass for this activity if one exists."""
        from cost.models import SeasonPass
        from django.db.models import Q
        
        activity_date = self.timestamp.date()
        
        # Check for season passes that cover this activity's ski area and date
        season_pass = SeasonPass.objects.filter(
            user=self.user,
            valid_from__lte=activity_date,
            valid_until__gte=activity_date
        ).filter(
            Q(skiarea=self.ski_area) |  # Direct ski area match
            Q(skiarea_network__members__member=self.ski_area)  # Ski area network match through members
        ).first()
        
        return season_pass
    

class Lap(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='laps')
    geom = models.LineStringField(null=True)
    lap_index = models.PositiveIntegerField(null=True)
    start_index_stream = models.PositiveIntegerField(null=True)
    end_index_stream = models.PositiveIntegerField(null=True)
    timestamp = models.DateTimeField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True)
    start_position = models.PointField()
    end_position = models.PointField()
    total_elapsed_time = models.DurationField()
    total_timer_time = models.DurationField()
    total_distance = models.FloatField()
    avg_speed = models.FloatField(null=True)
    max_speed = models.FloatField(null=True)
    min_altitude = models.FloatField(null=True)
    max_altitude = models.FloatField(null=True)
    total_calories = models.FloatField(null=True)
    total_ascent = models.FloatField(null=True)
    total_descent = models.FloatField(null=True)
    avg_heart_rate = models.PositiveIntegerField(null=True)
    max_heart_rate = models.PositiveIntegerField(null=True)
    lift_rides = models.ManyToManyField(Aerialway, through='LiftRide')

    class Meta:
        unique_together = ('activity', 'lap_index')


class Record(models.Model):
    lap = models.ForeignKey(Lap, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    position = models.PointField()
    # position_lat = models.DecimalField(max_digits=10, decimal_places=6)
    # position_long = models.DecimalField(max_digits=10, decimal_places=6)
    distance = models.FloatField(null=True)
    enhanced_speed = models.FloatField(null=True)
    enhanced_altitude = models.FloatField(null=True)
    heart_rate = models.PositiveIntegerField(null=True)


class LiftRide(models.Model):
    lap = models.ForeignKey(Lap, on_delete=models.CASCADE)
    aerialway = models.ForeignKey(Aerialway, on_delete=models.PROTECT)
    uphill = models.BooleanField(null=True)
    timestamp = models.DateTimeField()


class PisteRide(models.Model):
    lap = models.ForeignKey(Lap, on_delete=models.CASCADE)
    piste = models.ForeignKey(Piste, on_delete=models.PROTECT)
    timestamp = models.DateTimeField()


class Badge(models.Model):
    RARITY_CHOICES = [
        ('bronze', 'Bronze'),
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'),
        ('legendary', 'Legendary'),
    ]

    RARITY_ORDER = {
        'bronze': 1,
        'silver': 2,
        'gold': 3,
        'platinum': 4,
        'legendary': 5,
    }

    natural_key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=100, null=True, default='fa-solid fa-medal')
    rarity = models.CharField(max_length=20, choices=RARITY_CHOICES, default='bronze')
    sort_key = models.CharField(max_length=100, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    @property
    def rarity_order(self):
        """Get numeric order for rarity to enable proper sorting."""
        return self.RARITY_ORDER.get(self.rarity, 0)

    def __str__(self):
        return f"{self.name} ({self.natural_key})"

    @classmethod
    def get_by_natural_key(cls, natural_key):
        return cls.objects.get(natural_key=natural_key)


class ActivityBadge(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    achieved_on = models.DateTimeField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('activity', 'badge')

    def __str__(self):
        return f"{self.activity} - {self.badge}"
    

class ActivityPisteSegment(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='piste_segments')
    piste_segment = models.ForeignKey(PisteSegment, on_delete=models.PROTECT) # TODO: Cascade or protect?
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('activity', 'piste_segment')

    def __str__(self):
        return f"{self.activity} - {self.piste_segment}"
    
class StravaSyncSettings(models.Model):
    """
    Single row with global toggles for sync methods + scheduling.
    """
    # Singleton-ish: keep one row; enforce in admin/migrations or via get_solo()
    enable_scheduled_sync = models.BooleanField(default=False)
    schedule_every_minutes = models.PositiveIntegerField(
        default=15, validators=[MinValueValidator(1), MaxValueValidator(1440)]
    )

    enable_webhook_sync = models.BooleanField(default=False)

    # Webhook verification/secret material
    webhook_verify_token = models.CharField(
        max_length=64, blank=True, help_text="Used to verify Strava webhook challenge (GET)."
    )
    webhook_signing_secret = models.CharField(
        max_length=128, blank=True, help_text="Used to verify X-Strava-Signature HMAC (POST)."
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Strava Sync Settings"

    class Meta:
        verbose_name = "Strava Sync Settings"
        verbose_name_plural = "Strava Sync Settings"

class ActivityParserProfile(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='parser_profiles')
    version = models.PositiveIntegerField(default=1)
    operation = models.CharField(max_length=200)
    call_count = models.PositiveIntegerField()
    total_time = models.FloatField(help_text="Total time in seconds")
    avg_time = models.FloatField(help_text="Average time per call in seconds")
    max_time = models.FloatField(help_text="Maximum time for a single call in seconds")
    min_time = models.FloatField(help_text="Minimum time for a single call in seconds")
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('activity', 'operation', 'version')

    def __str__(self):
        return f"{self.activity} - {self.operation}"


class SummerActivityType(models.Model):
    """
    A user-selectable category for a manually tracked off-season (summer) activity,
    e.g. Hiking, Mountain Biking, Via Ferrata.

    Built-in types are global (``user`` is NULL) and seeded via data migration.
    Users may additionally create their own custom types (``user`` set).
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Owner of a custom type; NULL for built-in global types.",
    )
    name = models.CharField(max_length=100)
    natural_key = models.SlugField(
        max_length=120, unique=True,
        help_text="Stable identifier, unique across deployments (e.g. 'mountain-biking').",
    )
    icon = models.CharField(
        max_length=100, default='bi bi-bicycle',
        help_text="Bootstrap-icons class used in the UI.",
    )
    color = models.CharField(max_length=20, default='#2e7d32')
    sort_order = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['user'], name='summertype_user_idx'),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def for_user(cls, user):
        """Return active types available to a user: built-in globals + their own."""
        from django.db.models import Q
        return cls.objects.filter(is_active=True).filter(Q(user__isnull=True) | Q(user=user))


class SummerActivity(models.Model):
    """
    A manually tracked off-season activity that does not come from the GPS/lift
    parsing pipeline. Kept deliberately separate from :class:`Activity` so that
    all ski-specific views, statistics, badges and trip clustering (which query
    ``Activity``) remain winter-only by construction.

    Summer activities may optionally reference a Strava activity, be located at a
    ski area and be attributed to a :class:`cost.SeasonPass` so that their
    ``value`` offsets the effective cost of winter ski days.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='summer_activities')
    name = models.CharField(max_length=200)
    activity_type = models.ForeignKey(
        SummerActivityType, on_delete=models.PROTECT, related_name='activities',
    )
    date = models.DateField(help_text="Calendar date the activity took place.")
    timezone = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="IANA timezone name (e.g., Europe/Zurich).",
    )

    # Optional Strava link (manual association only; not auto-synced).
    strava_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True)
    strava_type = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Raw Strava sport_type (e.g. Run, Ride, Hike) when linked.",
    )

    # Location / season-pass attribution.
    ski_area = models.ForeignKey(
        SkiArea, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='summer_activities',
    )
    season_pass = models.ForeignKey(
        'cost.SeasonPass', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='summer_activities',
        help_text="Season pass covering this activity, if any.",
    )

    # Optional metrics (manual entry).
    distance = models.FloatField(null=True, blank=True, help_text="Distance in meters.")
    elevation_gain = models.FloatField(null=True, blank=True, help_text="Total ascent in meters.")
    duration = models.DurationField(null=True, blank=True)

    # Money: out-of-pocket cost paid, and ticket-equivalent value when covered.
    cost = MoneyField(
        max_digits=10, decimal_places=2, default_currency='CHF', null=True, blank=True,
        help_text="Out-of-pocket cost paid for this activity.",
    )
    value = MoneyField(
        max_digits=10, decimal_places=2, default_currency='CHF', null=True, blank=True,
        help_text="Equivalent ticket value when covered by a season pass.",
    )

    notes = models.TextField(blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "summer activity"
        verbose_name_plural = "summer activities"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', '-date'], name='summeract_user_date_idx'),
            models.Index(fields=['season_pass'], name='summeract_seasonpass_idx'),
        ]

    def __str__(self):
        return f"{self.name} ({self.date})"

    @property
    def is_covered(self):
        """True if this activity is attributed to a season pass."""
        return self.season_pass_id is not None

    def get_strava_url(self):
        return f"https://www.strava.com/activities/{self.strava_id}" if self.strava_id else None