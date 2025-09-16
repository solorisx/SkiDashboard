from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from djmoney.models.fields import MoneyField
from osm.models import Aerialway, SkiArea, SkiAreaBoundary, PisteSegment
from django.core.validators import MinValueValidator, MaxValueValidator


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

    ski_area = models.ForeignKey(SkiArea, on_delete=models.PROTECT, null=True)

    cost = MoneyField(max_digits=10, decimal_places=2, default_currency='CHF', null=True)
    value = MoneyField(max_digits=10, decimal_places=2, default_currency='CHF', null=True)

    def __str__(self):
        return f"{self.name}"

    def get_strava_url(self):
        return f"https://www.strava.com/activities/{self.strava_id}" if self.strava_id else None
    
    def get_num_lift_rides(self):
        return sum(lap.lift_rides.count() for lap in self.laps.all())
    
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


class Badge(models.Model):
    RARITY_CHOICES = [
        ('bronze', 'Bronze'),
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'),
        ('legendary', 'Legendary'),
    ]

    natural_key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=100, null=True, default='fa-solid fa-medal')
    rarity = models.CharField(max_length=20, choices=RARITY_CHOICES, default='bronze')
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

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