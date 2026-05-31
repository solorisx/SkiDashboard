# Seed built-in (global) summer activity types.

from django.db import migrations

# (natural_key, name, icon, color, sort_order)
DEFAULT_TYPES = [
    ('hiking', 'Hiking', 'bi bi-signpost-2', '#2e7d32', 10),
    ('trail-running', 'Trail Running', 'bi bi-person-walking', '#43a047', 20),
    ('mountain-biking', 'Mountain Biking', 'bi bi-bicycle', '#6d4c41', 30),
    ('road-cycling', 'Road Cycling', 'bi bi-bicycle', '#1e88e5', 40),
    ('via-ferrata', 'Via Ferrata', 'bi bi-ladder', '#e64a19', 50),
    ('climbing', 'Climbing', 'bi bi-triangle', '#8e24aa', 60),
    ('swimming', 'Swimming', 'bi bi-water', '#00acc1', 70),
    ('wellness', 'Wellness / Spa', 'bi bi-droplet-half', '#00897b', 80),
    ('other', 'Other', 'bi bi-asterisk', '#607d8b', 999),
]


def seed_types(apps, schema_editor):
    SummerActivityType = apps.get_model('activities', 'SummerActivityType')
    for natural_key, name, icon, color, sort_order in DEFAULT_TYPES:
        SummerActivityType.objects.update_or_create(
            natural_key=natural_key,
            defaults={
                'name': name,
                'icon': icon,
                'color': color,
                'sort_order': sort_order,
                'user': None,
                'is_active': True,
            },
        )


def unseed_types(apps, schema_editor):
    SummerActivityType = apps.get_model('activities', 'SummerActivityType')
    keys = [t[0] for t in DEFAULT_TYPES]
    SummerActivityType.objects.filter(user__isnull=True, natural_key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0026_summeractivitytype_summeractivity'),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
