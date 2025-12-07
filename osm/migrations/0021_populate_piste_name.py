# Generated manually on 2025-12-06

from django.db import migrations

def populate(apps, schema_editor):
    """Populate name field for existing pistes based on their OSM tags."""
    Piste = apps.get_model('osm', 'Piste')

    pistes_to_update_name = []
    pistes_to_update_ref = []

    pistes = Piste.objects.select_related('way').all()
    total_count = pistes.count()

    print(f"Found {total_count} pistes to process for name population")

    for piste in pistes.iterator(chunk_size=1000):
        way = piste.way

        if not piste.name and way.tags.get('piste:name'):
            piste.name = way.tags.get('piste:name')
            pistes_to_update_name.append(piste)

        if not piste.ref and way.tags.get('piste:ref'):
            piste.ref = way.tags.get('piste:ref')
            pistes_to_update_ref.append(piste)

        # Batch update every 500 pistes
        if len(pistes_to_update_name) >= 500:
            Piste.objects.bulk_update(pistes_to_update_name, ['name'])
            print(f"Updated {len(pistes_to_update_name)} piste names (batch)")
            pistes_to_update_name = []

        if len(pistes_to_update_ref) >= 500:
            Piste.objects.bulk_update(pistes_to_update_ref, ['ref'])
            print(f"Updated {len(pistes_to_update_ref)} piste refs (batch)")
            pistes_to_update_ref = []

    # Final batch update for remaining pistes
    if pistes_to_update_name:
        Piste.objects.bulk_update(pistes_to_update_name, ['name'])
        print(f"Updated {len(pistes_to_update_name)} piste names (final batch)")

    if pistes_to_update_ref:
        Piste.objects.bulk_update(pistes_to_update_ref, ['ref'])
        print(f"Updated {len(pistes_to_update_ref)} piste refs (final batch)")

    print(f"Migration complete. Processed {total_count} pistes")

def reverse_populate(apps, schema_editor):
    """Reverse operation - clear piste names and refs that match OSM tags."""
    Piste = apps.get_model('osm', 'Piste')

    pistes_to_clear_name = []
    pistes_to_clear_ref = []

    for piste in Piste.objects.select_related('way').iterator(chunk_size=1000):
        way = piste.way

        if piste.name and way.tags.get('piste:name') == piste.name:
            piste.name = None
            pistes_to_clear_name.append(piste)

        if piste.ref and way.tags.get('piste:ref') == piste.ref:
            piste.ref = None
            pistes_to_clear_ref.append(piste)

        # Batch update every 500 pistes
        if len(pistes_to_clear_name) >= 500:
            Piste.objects.bulk_update(pistes_to_clear_name, ['name'])
            pistes_to_clear_name = []

        if len(pistes_to_clear_ref) >= 500:
            Piste.objects.bulk_update(pistes_to_clear_ref, ['ref'])
            pistes_to_clear_ref = []

    # Final batch update for remaining pistes
    if pistes_to_clear_name:
        Piste.objects.bulk_update(pistes_to_clear_name, ['name'])

    if pistes_to_clear_ref:
        Piste.objects.bulk_update(pistes_to_clear_ref, ['ref'])


class Migration(migrations.Migration):
    dependencies = [
        ('osm', '0020_populate_piste_length'),
    ]

    operations = [
        migrations.RunPython(populate, reverse_populate),
    ]