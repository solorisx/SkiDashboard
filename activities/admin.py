from django.contrib import admin
from .models import Activity, ActivityBadge, Badge
from .models import StravaSyncSettings

admin.site.register(Activity)
admin.site.register(ActivityBadge)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ['name', 'natural_key', 'rarity', 'created_on']
    list_filter = ['rarity', 'created_on']
    search_fields = ['name', 'natural_key', 'description']
    readonly_fields = ['natural_key', 'name', 'description', 'icon', 'rarity', 'created_on', 'modified_on']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(StravaSyncSettings)
class StravaSyncSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "enable_scheduled_sync", "schedule_every_minutes",
        "enable_webhook_sync", "updated_at",
    )
    fieldsets = (
        ("Scheduling", {
            "fields": ("enable_scheduled_sync", "schedule_every_minutes"),
        }),
        ("Webhook", {
            "fields": ("enable_webhook_sync", "webhook_verify_token", "webhook_signing_secret"),
        }),
    )

    def has_add_permission(self, request):
        # Enforce single-row settings (optional)
        return not StravaSyncSettings.objects.exists()
