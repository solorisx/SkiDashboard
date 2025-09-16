# Generated manually for badge rarity and icon updates

from django.db import migrations


def update_badge_rarity_and_icons(apps, schema_editor):
    """
    Update existing badges with appropriate rarity levels and better icons
    """
    Badge = apps.get_model('activities', 'Badge')

    # Badge updates mapping: name -> (rarity, icon, description)
    badge_updates = {
        # Lift ride badges
        '5 lifts in a Day': ('bronze', 'fa-solid fa-cable-car', 'You rode 5 lifts in a single day!'),
        '10 lifts in a Day': ('silver', 'fa-solid fa-medal', 'You rode 10 lifts in a single day!'),
        '20 lifts in a Day': ('gold', 'fa-solid fa-trophy', 'You rode 20 lifts in a single day!'),

        # Elevation badges
        "10'000hm in a Day": ('gold', 'fa-solid fa-mountain', 'You climbed 10\'000m in a single day!'),
        "20'000hm in a Day": ('platinum', 'fa-solid fa-mountain-sun', 'You climbed 20\'000m in a single day!'),

        # Area exploration badges
        'First day in a Ski Area': ('silver', 'fa-solid fa-map-location-dot', 'You visited a new ski area for the first time!'),
    }

    # Update/create specific badges
    for badge_name, (rarity, icon, description) in badge_updates.items():
        Badge.objects.update_or_create(
            name=badge_name,
            defaults={
                'rarity': rarity,
                'icon': icon,
                'description': description
            }
        )

    # Create/update streak badges for consecutive days (1-10 days)
    for days in range(2, 11):  # 2-10 days
        # Determine rarity based on streak length
        if days <= 3:
            rarity = 'bronze'
            icon = 'fa-solid fa-calendar-check'
        elif days <= 7:
            rarity = 'silver'
            icon = 'fa-solid fa-fire'
        else:  # 8-10 days
            rarity = 'gold'
            icon = 'fa-solid fa-fire'

        # General skiing streak badge
        Badge.objects.update_or_create(
            name=f'{days} days in a row',
            defaults={
                'rarity': rarity,
                'icon': icon,
                'description': f'You skied {days} days in a row!'
            }
        )

        # Ski area specific streak badge
        ski_area_rarity = 'bronze' if days <= 3 else 'silver' if days <= 7 else 'gold'
        ski_area_icon = 'fa-solid fa-calendar-check' if days <= 3 else 'fa-solid fa-map-pin'

        Badge.objects.update_or_create(
            name=f'{days} days in a row in a Ski Area',
            defaults={
                'rarity': ski_area_rarity,
                'icon': ski_area_icon,
                'description': f'You visited the same ski area {days} days in a row!'
            }
        )

    # Handle any existing streak badges beyond 10 days with dynamic rarity
    existing_streak_badges = Badge.objects.filter(name__contains='days in a row')
    for badge in existing_streak_badges:
        try:
            days = int(badge.name.split()[0])

            # Only update if it's beyond our predefined range
            if days > 10:
                if days <= 14:
                    rarity = 'gold'
                    icon = 'fa-solid fa-crown'
                elif days <= 30:
                    rarity = 'platinum'
                    icon = 'fa-solid fa-crown'
                else:  # 30+ days
                    rarity = 'legendary'
                    icon = 'fa-solid fa-gem'

                badge.rarity = rarity
                badge.icon = icon
                badge.save()

        except (ValueError, IndexError):
            # If we can't parse the number, leave as is
            pass

    # Set default rarity for any other badges that don't have a rarity set
    badges_without_proper_rarity = Badge.objects.filter(rarity='bronze').exclude(
        name__in=badge_updates.keys()
    ).exclude(name__contains='days in a row')

    for badge in badges_without_proper_rarity:
        # Assign appropriate icons based on badge name patterns
        if 'lift' in badge.name.lower():
            badge.icon = 'fa-solid fa-cable-car'
        elif 'mountain' in badge.name.lower() or 'hm' in badge.name.lower():
            badge.icon = 'fa-solid fa-mountain'
        elif 'area' in badge.name.lower() or 'ski' in badge.name.lower():
            badge.icon = 'fa-solid fa-map-location-dot'
        elif 'speed' in badge.name.lower():
            badge.icon = 'fa-solid fa-gauge-high'
        elif 'distance' in badge.name.lower():
            badge.icon = 'fa-solid fa-route'
        else:
            badge.icon = 'fa-solid fa-award'
        badge.save()


def reverse_update_badge_rarity_and_icons(apps, schema_editor):
    """
    Reverse the migration by setting all badges back to bronze rarity and default icon
    """
    Badge = apps.get_model('activities', 'Badge')
    Badge.objects.all().update(rarity='bronze', icon='fa-solid fa-medal')


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0014_badge_rarity'),
    ]

    operations = [
        migrations.RunPython(
            update_badge_rarity_and_icons,
            reverse_update_badge_rarity_and_icons
        ),
    ]