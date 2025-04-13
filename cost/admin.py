from django.contrib import admin

# Register your models here.

from .models import SeasonPass, TicketPrice

admin.site.register(SeasonPass)
admin.site.register(TicketPrice)



