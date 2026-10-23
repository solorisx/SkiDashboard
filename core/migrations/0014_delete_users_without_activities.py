"""One-time cleanup of spam signups: delete every user that has no activities.

Staff, superusers and premium users are kept even without activities. Not reversible.
"""

from django.db import migrations


def delete_users_without_activities(apps, schema_editor):
    User = apps.get_model("auth", "User")
    users = User.objects.filter(activity__isnull=True, is_staff=False, is_superuser=False).exclude(
        userprofile__is_premium=True
    )
    user_ids = list(users.values_list("pk", flat=True))
    User.objects.filter(pk__in=user_ids).delete()
    print(f"\n  Deleted {len(user_ids)} users without activities")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_alter_premiumconfig_id"),
        ("activities", "0025_activity_strava_description_updated"),
        ("cost", "0004_alter_seasonpass_price_currency_and_more"),
        ("account", "__latest__"),
        ("socialaccount", "__latest__"),
    ]

    operations = [
        migrations.RunPython(delete_users_without_activities, migrations.RunPython.noop),
    ]
