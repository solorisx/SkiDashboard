from django.db import models
from djmoney.models.fields import MoneyField
from osm.models import SkiArea, SkiAreaNetwork
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
from datetime import datetime
from activities.models import Activity
from django.utils.timezone import make_aware
import logging

logger = logging.getLogger(__name__)

class TicketPrice(models.Model):
    skiarea = models.ForeignKey(SkiArea, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, null=True, blank=True)
    type = models.TextChoices('Type', 'daypass multidaypass seasonpass')
    price = MoneyField(max_digits=14, decimal_places=2, default_currency='CHF')
    valid_from = models.DateField()
    valid_until = models.DateField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} - {self.price} - {self.skiarea}'

    def is_valid(self, date):
        return self.valid_from <= date <= self.valid_until
    
    def clean(self):
        if self.valid_from > self.valid_until:
            raise ValidationError('valid_from must be before valid_until')
        if self.price.amount < 0:
            raise ValidationError('price must be positive')
        if TicketPrice.objects.filter(
            skiarea=self.skiarea, 
            type=self.type
            ).filter(
                Q(valid_to__gte=self.valid_from, valid_to__lte=self.valid_to) |  # Overlaps with valid_to
                Q(valid_from__lte=self.valid_to, valid_from__gte=self.valid_from)  # Overlaps with valid_from
            ).exclude(pk=self.pk).exists():
            raise ValidationError('A price for this ski area, type and date range already exists')
        super().clean()


class SeasonPass(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    skiarea = models.ForeignKey(SkiArea, on_delete=models.CASCADE, related_name='season_passes', null=True, blank=True)
    skiarea_network = models.ForeignKey(SkiAreaNetwork, on_delete=models.CASCADE, related_name='season_passes_network', null=True, blank=True)
    valid_from = models.DateField()
    valid_until = models.DateField()
    price = MoneyField(max_digits=14, decimal_places=2, default_currency='CHF')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_active(self):
        today = datetime.now().date()
        return self.valid_from <= today <= self.valid_until

    def get_valid_activities(self, date_from: datetime = make_aware(datetime.min), date_until: datetime = make_aware(datetime.max)):
        """
        Returns all activities within the valid period of this season pass.
        Includes activities from the ski area and ski areas belonging to the ski area network.
        """
        start_date = max(self.valid_from, date_from.date())
        end_date = min(self.valid_until, date_until.date())

        logger.debug(f"Getting valid activities for SeasonPass {self.id} from {start_date} to {end_date}")

        # Fetch ski areas from SkiAreaNetworkMember, considering NULL valid_to as "no expiry"
        ski_areas_in_network = SkiArea.objects.filter(
            skiareanetworkmember__ski_area_network=self.skiarea_network
        ).filter(
            (Q(skiareanetworkmember__valid_from__lte=self.valid_until) | Q(skiareanetworkmember__valid_from__isnull=True)) &  # Start date must be before season pass expiry or NULL
            (Q(skiareanetworkmember__valid_to__gte=self.valid_from) | Q(skiareanetworkmember__valid_to__isnull=True))  # Valid if no expiry or within range
        ).values_list("id", flat=True) if self.skiarea_network else []

        return Activity.objects.filter(
            user=self.user,
            timestamp__range=(start_date, end_date),
        ).filter(
            ski_area=self.skiarea  # Activities from the primary ski area
        ) | Activity.objects.filter(
            user=self.user,
            timestamp__range=(start_date, end_date),
            ski_area_id__in=ski_areas_in_network  # Activities from ski areas in the network
        )

    def count_valid_activities(self, date_from: datetime = make_aware(datetime.min), date_until: datetime = make_aware(datetime.max)):
        return self.get_valid_activities(date_from, date_until).count()

    def __str__(self):
        return f'{self.user} - {self.skiarea}{self.skiarea_network} - {self.valid_from} - {self.valid_until}'

    def clean(self):
        if self.skiarea and self.skiarea_network:
            raise ValidationError('A season pass must be for either a ski area or a ski area network, not both')
        # if self.valid_from > self.valid_until:
        #     raise ValidationError('valid_from must be before valid_until')
        # if self.price < 0:
        #     raise ValidationError('price must be positive')
        # if SeasonPass.objects.filter(
        #     skiarea=self.skiarea, 
        #     ).filter(
        #         Q(valid_until__gte=self.valid_from, valid_until__lte=self.valid_until) |  # Overlaps with valid_to
        #         Q(valid_from__lte=self.valid_until, valid_from__gte=self.valid_from)  # Overlaps with valid_from
        #     ).exclude(pk=self.pk).exists():
        #     raise ValidationError('A season pass for this ski area and date range already exists')
        super().clean()
        