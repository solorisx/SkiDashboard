from django.db import models
from djmoney.models.fields import MoneyField
from osm.models import SkiArea, SkiAreaNetwork
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q


class Transaction(models.Model):
    amount = MoneyField(max_digits=14, decimal_places=2, default_currency='CHF')
    description = models.CharField(max_length=255)
    skiarea = models.ForeignKey(SkiArea, on_delete=models.PROTECT, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.amount} - {self.description}'
    

class TicketPrice(models.Model):
    skiarea = models.ForeignKey(SkiArea, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, null=True, blank=True)
    type = models.TextChoices('Type', 'daypass multidaypass seasonpass')
    price = MoneyField(max_digits=14, decimal_places=2, default_currency='CHF')
    valid_from = models.DateField()
    valid_until = models.DateField()
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
        