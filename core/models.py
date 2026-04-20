from django.contrib.gis.db import models
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)


PAYMENT_SOURCE_CHOICES = [
    ('buymeacoffee', 'BuyMeACoffee'),
    ('manual', 'Manual'),
]

PREMIUM_PLAN_CHOICES = [
    ('monthly', 'Monthly'),
    ('yearly', 'Yearly'),
]


class PremiumConfig(models.Model):
    """Singleton model — staff configure premium pricing and BMC thresholds here."""
    monthly_price_usd = models.DecimalField(max_digits=6, decimal_places=2, default=5.00)
    yearly_price_usd = models.DecimalField(max_digits=6, decimal_places=2, default=50.00)
    # Minimum BuyMeACoffee donation to trigger each plan
    monthly_threshold_usd = models.DecimalField(max_digits=6, decimal_places=2, default=5.00)
    yearly_threshold_usd = models.DecimalField(max_digits=6, decimal_places=2, default=50.00)

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Premium Configuration"


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

    # User preferences and opt-ins
    opt_in_newsletter = models.BooleanField(default=False, help_text="Receive occassional newsletters and updates about the app (no more than 4 per year)")
    opt_in_summary_email = models.BooleanField(default=False, help_text="Receive summary of new activities by email")
    opt_in_strava_write = models.BooleanField(default=False, help_text="Allow app to update Strava activity descriptions with the ridden lifts")

    # Profile completion tracking
    profile_confirmed = models.BooleanField(default=False, help_text="User has confirmed their initial profile settings")

    # Premium membership
    is_premium = models.BooleanField(default=False, db_index=True)
    premium_plan = models.CharField(max_length=20, choices=PREMIUM_PLAN_CHOICES, null=True, blank=True)
    premium_expires_at = models.DateTimeField(null=True, blank=True)
    premium_granted_at = models.DateTimeField(null=True, blank=True)
    premium_payment_source = models.CharField(max_length=50, choices=PAYMENT_SOURCE_CHOICES, null=True, blank=True)
    premium_granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='premium_grants'
    )
    premium_expiry_30d_notified = models.BooleanField(default=False)
    premium_expiry_7d_notified = models.BooleanField(default=False)

    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def is_premium_active(self):
        from django.utils import timezone
        return self.is_premium and (
            self.premium_expires_at is None or self.premium_expires_at > timezone.now()
        )

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