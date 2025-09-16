# Migration to add natural_key field to Badge model and populate existing badges

from django.db import migrations, models
import re


def assign_natural_keys_to_badges(apps, schema_editor):
    """
    Assign natural keys to existing badges based on their names
    """
    Badge = apps.get_model('activities', 'Badge')

    # Mapping of badge name patterns to natural keys
    badge_mappings = {
        # Exact matches for predefined badges
        '5 lifts in a Day': 'LIFTS_5_DAY',
        '10 lifts in a Day': 'LIFTS_10_DAY',
        '20 lifts in a Day': 'LIFTS_20_DAY',
        "10'000hm in a Day": 'ELEVATION_10K_DAY',
        "20'000hm in a Day": 'ELEVATION_20K_DAY',
        'First day in a Ski Area': 'FIRST_SKI_AREA',
    }

    # Update predefined badges
    for badge_name, natural_key in badge_mappings.items():
        try:
            badge = Badge.objects.get(name=badge_name)
            badge.natural_key = natural_key
            badge.save()
        except Badge.DoesNotExist:
            # Badge doesn't exist yet, will be created later
            pass

    # Handle dynamic streak badges
    for badge in Badge.objects.filter(name__contains='days in a row'):
        if badge.natural_key:  # Skip if already assigned
            continue

        # Extract number of days from badge name
        match = re.match(r'(\d+) days in a row( in a Ski Area)?', badge.name)
        if match:
            days = match.group(1)
            is_ski_area_specific = match.group(2) is not None

            if is_ski_area_specific:
                natural_key = f'STREAK_SKI_AREA_{days}D'
            else:
                natural_key = f'STREAK_GENERAL_{days}D'

            badge.natural_key = natural_key
            badge.save()

    # Handle any remaining badges without natural keys
    remaining_badges = Badge.objects.filter(natural_key__isnull=True)
    for badge in remaining_badges:
        # Generate a natural key based on the badge name
        # Replace spaces with underscores, convert to uppercase, remove special chars
        natural_key = re.sub(r'[^A-Z0-9_]', '', badge.name.upper().replace(' ', '_').replace("'", ''))
        # Ensure uniqueness by appending a number if needed
        base_key = natural_key
        counter = 1
        while Badge.objects.filter(natural_key=natural_key).exists():
            natural_key = f"{base_key}_{counter}"
            counter += 1

        badge.natural_key = natural_key
        badge.save()


def reverse_assign_natural_keys(apps, schema_editor):
    """
    Reverse the natural key assignment by clearing all natural_key values
    """
    Badge = apps.get_model('activities', 'Badge')
    Badge.objects.all().update(natural_key=None)


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0015_update_badge_rarity_and_icons'),
    ]

    operations = [
        # Add the natural_key field (allow null initially)
        migrations.AddField(
            model_name='badge',
            name='natural_key',
            field=models.CharField(max_length=100, null=True),
        ),

        # Populate natural keys for existing badges
        migrations.RunPython(
            assign_natural_keys_to_badges,
            reverse_assign_natural_keys
        ),

        # Make natural_key unique and non-null
        migrations.AlterField(
            model_name='badge',
            name='natural_key',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]