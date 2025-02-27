from django.db import migrations

def migrate_ski_areas(apps, schema_editor):
    SkiArea = apps.get_model('SkiingDashboardApp', 'SkiArea')
    SkiAreaBoundary = apps.get_model('SkiingDashboardApp', 'SkiAreaBoundary')

    for skiarea in SkiAreaBoundary.objects.all():
        SkiArea.objects.get_or_create(
            osm_id=skiarea.way.osm_id,
            osm_type='area',
            name=SkiAreaBoundary.name,
            way=skiarea.way,
            geom=skiarea.geom
        )

class Migration(migrations.Migration):

    dependencies = [
        ('SkiingDashboardApp', '0036_alter_skiarea_name'),
    ]

    operations = [
        migrations.RunPython(migrate_ski_areas),
    ]