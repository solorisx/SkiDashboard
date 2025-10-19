from django.contrib import admin
from django.contrib import messages
from .models import Activity, ActivityBadge, Badge
from .models import StravaSyncSettings


def update_strava_descriptions(modeladmin, request, queryset):
    """Admin action to update Strava activity descriptions for selected activities."""
    from .activity_parser import ActivityParser

    parser = ActivityParser()
    success_count = 0
    error_count = 0
    skipped_count = 0

    for activity in queryset:
        if not activity.strava_id:
            skipped_count += 1
            continue

        try:
            success = parser.update_strava_description(activity)
            if success:
                success_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            error_count += 1
            messages.error(request, f"Error updating activity {activity.id}: {str(e)}")

    if success_count > 0:
        messages.success(request, f"Successfully updated {success_count} Strava description(s).")
    if skipped_count > 0:
        messages.info(request, f"Skipped {skipped_count} activity/activities (no Strava ID or user opted out).")
    if error_count > 0:
        messages.error(request, f"Failed to update {error_count} activity/activities.")

update_strava_descriptions.short_description = "Update Strava descriptions for selected activities"


class SkiAreaWithActivitiesFilter(admin.SimpleListFilter):
    """Filter ski areas to only show those that have activities."""
    title = 'ski area'
    parameter_name = 'ski_area'

    def lookups(self, request, model_admin):
        """Return only ski areas that have at least one activity."""
        from osm.models import SkiArea
        # Get ski areas that are referenced by at least one activity
        ski_areas = SkiArea.objects.filter(
            activity__isnull=False
        ).distinct().order_by('name')
        return [(ski_area.id, ski_area.name) for ski_area in ski_areas]

    def queryset(self, request, queryset):
        """Filter the queryset based on the selected ski area."""
        if self.value():
            return queryset.filter(ski_area__id=self.value())
        return queryset


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'user', 'start_time', 'ski_area', 'num_lift_rides', 'strava_id']
    list_filter = [SkiAreaWithActivitiesFilter, 'start_time', 'user']
    search_fields = ['name', 'user__username', 'strava_id']
    actions = [update_strava_descriptions]
    readonly_fields = ['strava_id', 'created_on', 'modified_on', 'processed_on']


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
