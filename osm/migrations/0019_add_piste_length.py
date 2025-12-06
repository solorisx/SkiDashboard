# Generated manually on 2025-12-06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('osm', '0018_add_verified_on'),
    ]

    operations = [
        migrations.AddField(
            model_name='piste',
            name='length',
            field=models.FloatField(
                blank=True,
                null=True,
                help_text='Length in meters (EPSG:3857)'
            ),
        ),
    ]
