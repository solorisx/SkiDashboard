from django.contrib import admin
from .models import Activity, ActivityBadge, Badge
from .models import StravaSyncSettings

admin.site.register(Activity)
admin.site.register(ActivityBadge)
admin.site.register(Badge)

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
