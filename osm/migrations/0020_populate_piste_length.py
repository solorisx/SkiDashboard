# Generated manually on 2025-12-06

from django.db import migrations
from django.db.models import Q


def populate_piste_lengths(apps, schema_editor):
    """Populate length field for existing downhill, line-based pistes."""
    Piste = apps.get_model('osm', 'Piste')
    from django.contrib.gis.geos.error import GEOSException

    count = 0
    updated_count = 0

    # Get downhill pistes with geometry
    downhill_pistes = Piste.objects.filter(
        geom__isnull=False
    ).filter(
        Q(piste_type='downhill') | Q(piste_type__isnull=True)
    )

    print(f"Found {downhill_pistes.count()} downhill pistes with geometry")

    for piste in downhill_pistes:
        count += 1
        try:
            # Check if line-based (simplified check - can't call is_area() in migration)
            if piste.geom.geom_type == 'LineString':
                metric_geom = piste.geom.transform(3857, clone=True)
                piste.length = metric_geom.length
                piste.save(update_fields=['length'])
                updated_count += 1

                if updated_count % 100 == 0:
                    print(f"Processed {updated_count} pistes...")
        except (GEOSException, AttributeError) as e:
            print(f"Error processing piste {piste.id}: {e}")
            pass

    print(f"Populated length for {updated_count} out of {count} downhill pistes")


def reverse_populate(apps, schema_editor):
    """Reverse operation - clear all piste lengths."""
    Piste = apps.get_model('osm', 'Piste')
    Piste.objects.all().update(length=None)


class Migration(migrations.Migration):

    dependencies = [
        ('osm', '0019_add_piste_length'),
    ]

    operations = [
        migrations.RunPython(populate_piste_lengths, reverse_populate),
    ]
