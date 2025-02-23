from django.contrib.gis.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from djmoney.models.fields import MoneyField
from .osm_models import SkiArea, SkiAreaBoundary

class ValidDuring(models.TextChoices):
    winter = 'winter', 'Winter'
    summer = 'summer', 'Summer'
    all = 'all', 'All Seasons'


class SkiAreaNetwork(models.Model):
    members = models.ManyToManyField(ContentType, through='SkiAreaNetworkMember', related_name='networks')
    name = models.CharField(max_length=255, unique=True)
    season_pass_price = MoneyField(max_digits=10, decimal_places=2, default_currency='CHF', null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ski Area Network {self.name} for {self.ski_area.name}"
    
class SkiAreaNetworkMember(models.Model):
    ski_area_network = models.ForeignKey(SkiAreaNetwork, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    member = GenericForeignKey('content_type', 'object_id')
    valid_from = models.DateField(null=True)
    valid_to = models.DateField(null=True)
    max_days = models.PositiveIntegerField(default=365)
    valid_during = models.CharField(max_length=10, choices=ValidDuring.choices, default=ValidDuring.all)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['ski_area_network', 'content_type', 'object_id']

    def __str__(self):
        return f"{self.ski_area_network.name} - {self.member.name} ({self.valid_from} - {self.valid_to})"
