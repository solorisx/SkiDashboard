from django.contrib.gis.db import models
from django.contrib.auth.models import User
from .osm_models import Aerialway, SkiArea

class Activity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
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
    num_laps = models.PositiveIntegerField(null=True)
    avg_heart_rate = models.PositiveIntegerField(null=True)
    max_heart_rate = models.PositiveIntegerField(null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    ski_area = models.ForeignKey(SkiArea, on_delete=models.PROTECT, null=True)

    def get_strava_url(self):
        return f"https://www.strava.com/activities/{self.strava_id}" if self.strava_id else None
    
class Lap(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='laps')
    lap_index = models.PositiveIntegerField(null=True)
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
    timestamp = models.DateTimeField()

