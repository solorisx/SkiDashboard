from django.contrib.gis.db import models
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    beta_tester = models.BooleanField(default=False)
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    metric_units = models.BooleanField(default=True)
    dark_mode = models.BooleanField(default=False)
    last_strava_sync = models.DateTimeField(null=True)
    max_strava_sync = models.IntegerField(default=360)

    # Lift type preferences - list of aerialway types to exclude
    excluded_lift_types = models.JSONField(default=list, blank=True, help_text="Aerialway types to exclude from statistics")

    # Custom season boundaries
    season_start_month = models.IntegerField(default=7, help_text="Month when ski season starts (1-12)")
    season_start_day = models.IntegerField(default=1, help_text="Day when ski season starts (1-31)")

    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def get_season_start_date(self, year):
        """Get season start date for a given year using user's preferences."""
        from datetime import datetime
        return datetime(year, self.season_start_month, self.season_start_day)

    def get_season_end_date(self, year):
        """Get season end date for a given year using user's preferences."""
        from datetime import timedelta
        return self.get_season_start_date(year + 1) - timedelta(days=1)

    def __str__(self):
        return f"Profile for {self.user.username}"
    
    def save(self, *args, **kwargs):
        # check whether excluded_lift_types has changed
        if self.pk:
            orig = UserProfile.objects.get(pk=self.pk)
            if orig.excluded_lift_types != self.excluded_lift_types:
                logger.info(f"User {self.user.username} changed excluded_lift_types from {orig.excluded_lift_types} to {self.excluded_lift_types}")
                super().save(*args, **kwargs)
                from activities.tasks import recalculate_completeness_task, reassign_badges_task
                recalculate_completeness_task.delay(self.user.id)
                reassign_badges_task.delay(self.user.id)
                return
        super().save(*args, **kwargs)