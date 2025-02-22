from django.contrib.gis.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    metric_units = models.BooleanField(default=True)
    dark_mode = models.BooleanField(default=False)
    last_strava_sync = models.DateTimeField(null=True)
    max_strava_sync = models.IntegerField(default=90)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
