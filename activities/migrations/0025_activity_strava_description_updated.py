from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0024_trip_activity_trip'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='strava_description_updated',
            field=models.BooleanField(default=False, help_text='True if Strava description has been updated with lift rides'),
        ),
    ]
