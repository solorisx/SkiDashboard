from django.db import migrations
from django.contrib.gis.db.models.functions import Transform, Length
from django.db import models

def update_piste_segment_lengths(apps, schema_editor):
    PisteSegment = apps.get_model('osm', 'PisteSegment')

    # Transform to a metric projection (EPSG:3857) before calculating length
    PisteSegment.objects.update(length=Length(Transform('geom', 3857)))

class Migration(migrations.Migration):

    dependencies = [
        ('osm', '0013_alter_waynode_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='pistesegment',
            name='length',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.RunPython(update_piste_segment_lengths),
    ]
