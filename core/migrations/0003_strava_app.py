from django.conf import settings
from django.db import migrations

def up(apps, schema_editor):
    import os
    SocialApp = apps.get_model("socialaccount", "SocialApp")

    provider_id = os.getenv("ALLAUTH_STRAVA_PROVIDER_ID", "strava")  # default
    client_id = os.getenv("STRAVA_CLIENT_ID")
    secret = os.getenv("STRAVA_CLIENT_SECRET")
    app_name = os.getenv("STRAVA_APP_NAME", "Strava")

    if not client_id or not secret:
        # Nothing to do without credentials in env
        return

    # Upsert the SocialApp
    social_app, _ = SocialApp.objects.get_or_create(
        provider=provider_id,
        name=app_name,
        defaults={"client_id": client_id, "secret": secret},
    )
    # Keep creds in sync with env
    changed = False
    if social_app.client_id != client_id:
        social_app.client_id = client_id; changed = True
    if social_app.secret != secret:
        social_app.secret = secret; changed = True
    if changed:
        social_app.save(update_fields=["client_id", "secret"])

def down(apps, schema_editor):
    # Keep it non-destructive (don’t drop the app on rollback)
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_userprofile_beta_tester"),
        ("socialaccount", "0001_initial"),  # ensure socialaccount is available
    ]
    operations = [migrations.RunPython(up, down)]
