from datetime import timedelta
from .models import Activity, Badge, ActivityBadge


BADGE_CONFIGS = {
    # Lift ride badges
    'LIFTS_5_DAY': {
        'name': '5 lifts in a Day',
        'description': 'You rode 5 lifts in a single day!',
        'icon': 'fa-solid fa-cable-car',
        'rarity': 'bronze',
        'sort_key': '100_lifts_5_day'
    },
    'LIFTS_10_DAY': {
        'name': '10 lifts in a Day',
        'description': 'You rode 10 lifts in a single day!',
        'icon': 'fa-solid fa-medal',
        'rarity': 'silver',
        'sort_key': '200_lifts_10_day'
    },
    'LIFTS_20_DAY': {
        'name': '20 lifts in a Day',
        'description': 'You rode 20 lifts in a single day!',
        'icon': 'fa-solid fa-trophy',
        'rarity': 'gold',
        'sort_key': '300_lifts_20_day'
    },

    # Elevation badges
    'ELEVATION_10K_DAY': {
        'name': "10'000hm in a Day",
        'description': "You climbed 10'000m in a single day!",
        'icon': 'fa-solid fa-mountain',
        'rarity': 'gold',
        'sort_key': '300_elevation_10k_day'
    },
    'ELEVATION_20K_DAY': {
        'name': "20'000hm in a Day",
        'description': "You climbed 20'000m in a single day!",
        'icon': 'fa-solid fa-mountain-sun',
        'rarity': 'platinum',
        'sort_key': '400_elevation_20k_day'
    },

    # Exploration badges
    'FIRST_SKI_AREA': {
        'name': 'First day in a Ski Area',
        'description': 'You visited a new ski area for the first time!',
        'icon': 'fa-solid fa-map-location-dot',
        'rarity': 'silver',
        'sort_key': '200_first_ski_area'
    },

    # Completeness badges
    'COMPLETENESS_25': {
        'name': 'Explorer',
        'description': 'You rode 25% of lifts in a ski area!',
        'icon': 'fa-solid fa-compass',
        'rarity': 'bronze',
        'sort_key': '100_completeness_25'
    },
    'COMPLETENESS_50': {
        'name': 'Area Scout',
        'description': 'You rode 50% of lifts in a ski area!',
        'icon': 'fa-solid fa-map',
        'rarity': 'silver',
        'sort_key': '200_completeness_50'
    },
    'COMPLETENESS_75': {
        'name': 'Mountain Master',
        'description': 'You rode 75% of lifts in a ski area!',
        'icon': 'fa-solid fa-mountain',
        'rarity': 'gold',
        'sort_key': '300_completeness_75'
    },
    'COMPLETENESS_100': {
        'name': 'Area Conqueror',
        'description': 'You rode 100% of lifts in a ski area!',
        'icon': 'fa-solid fa-crown',
        'rarity': 'platinum',
        'sort_key': '400_completeness_100'
    },

    # Daily completeness badges
    'DAILY_COMPLETENESS_25': {
        'name': 'Daily Explorer',
        'description': 'You rode 25% of lifts in a ski area in one day!',
        'icon': 'fa-solid fa-calendar-day',
        'rarity': 'bronze',
        'sort_key': '100_daily_completeness_25'
    },
    'DAILY_COMPLETENESS_50': {
        'name': 'Daily Scout',
        'description': 'You rode 50% of lifts in a ski area in one day!',
        'icon': 'fa-solid fa-calendar-check',
        'rarity': 'silver',
        'sort_key': '200_daily_completeness_50'
    },
    'DAILY_COMPLETENESS_75': {
        'name': 'Daily Master',
        'description': 'You rode 75% of lifts in a ski area in one day!',
        'icon': 'fa-solid fa-calendar-star',
        'rarity': 'gold',
        'sort_key': '300_daily_completeness_75'
    },
    'DAILY_COMPLETENESS_100': {
        'name': 'Daily Conqueror',
        'description': 'You rode 100% of lifts in a ski area in one day',
        'icon': 'fa-solid fa-calendar-crown',
        'sort_key': '400_daily_completeness_100',
        'rarity': 'platinum'
    },

    # Lift variety badges
    'LIFT_VARIETY_5': {
        'name': 'Lift Sampler',
        'description': 'You used 5 different lifts in one day!',
        'icon': 'fa-solid fa-list',
        'rarity': 'bronze',
        'sort_key': '100_lift_variety_5'
    },
    'LIFT_VARIETY_10': {
        'name': 'Lift Collector',
        'description': 'You used 10 different lifts in one day!',
        'icon': 'fa-solid fa-grip',
        'rarity': 'silver',
        'sort_key': '200_lift_variety_10'
    },
    'LIFT_VARIETY_15': {
        'name': 'Lift Enthusiast',
        'description': 'You used 15 different lifts in one day!',
        'icon': 'fa-solid fa-star',
        'rarity': 'gold',
        'sort_key': '300_lift_variety_15'
    },
    'LIFT_VARIETY_20': {
        'name': 'Lift Connoisseur',
        'description': 'You used 20 different lifts in one day!',
        'icon': 'fa-solid fa-gem',
        'sort_key': '300_lift_variety_20',
        'rarity': 'gold'
    },
    'LIFT_VARIETY_30': {
        'name': 'Lift Aficionado',
        'description': 'You used 30 different lifts in one day!',
        'icon': 'fa-solid fa-crown',
        'rarity': 'platinum',
        'sort_key': '400_lift_variety_30'
    },
}


def get_streak_badge_config(days, ski_area_specific=False):
    """Generate badge configuration for streak badges"""
    # Determine rarity and icon based on streak length
    if days <= 3:
        rarity = 'bronze'
        icon = 'fa-solid fa-calendar-check'
        sort_key = '100_streak_3d'
    elif days <= 7:
        rarity = 'silver'
        icon = 'fa-solid fa-fire' if not ski_area_specific else 'fa-solid fa-map-pin'
        sort_key = '200_streak_7d'
    elif days <= 14:
        rarity = 'gold'
        icon = 'fa-solid fa-fire' if not ski_area_specific else 'fa-solid fa-map-pin'
        sort_key = '300_streak_14d'
    elif days <= 30:
        rarity = 'platinum'
        icon = 'fa-solid fa-crown'
        sort_key = '400_streak_30d'
    else:
        rarity = 'legendary'
        icon = 'fa-solid fa-gem'
        sort_key = '500_streak_30d_plus'

    if ski_area_specific:
        natural_key = f'STREAK_SKI_AREA_{days}D'
        name = f'{days} days in a row in a Ski Area'
        description = f'You visited the same ski area {days} days in a row!'
    else:
        natural_key = f'STREAK_GENERAL_{days}D'
        name = f'{days} days in a row'
        description = f'You skied {days} days in a row!'

    return natural_key, {
        'name': name,
        'description': description,
        'icon': icon,
        'rarity': rarity,
        'sort_key': sort_key
    }


def get_or_create_badge_by_natural_key(natural_key, **defaults):
    """Get or create a badge using its natural key"""
    if natural_key in BADGE_CONFIGS:
        config = BADGE_CONFIGS[natural_key]
        badge, _ = Badge.objects.update_or_create(
            natural_key=natural_key,
            defaults={**config, **defaults}
        )
        return badge, _
    else:
        # For dynamic badges like streaks
        badge, _ = Badge.objects.update_or_create(
            natural_key=natural_key,
            defaults=defaults
        )
        return badge, _


def assign_badges(activity: Activity):

    # 5 rides in a day
    if activity.num_lift_rides and activity.num_lift_rides >= 5:
        badge, _ = get_or_create_badge_by_natural_key('LIFTS_5_DAY')
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

    # 10 rides in a day
    if activity.num_lift_rides and activity.num_lift_rides >= 10:
        badge, _ = get_or_create_badge_by_natural_key('LIFTS_10_DAY')
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

    # 20 rides in a day
    if activity.num_lift_rides and activity.num_lift_rides >= 20:
        badge, _ = get_or_create_badge_by_natural_key('LIFTS_20_DAY')
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

    # 10'000hm in a day
    if activity.total_ascent and activity.total_ascent >= 10000:
        badge, _ = get_or_create_badge_by_natural_key('ELEVATION_10K_DAY')
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

    # 20'000hm in a day
    if activity.total_ascent and activity.total_ascent >= 20000:
        badge, _ = get_or_create_badge_by_natural_key('ELEVATION_20K_DAY')
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

    # first day in a ski area - award for first visit to each unique ski area
    if activity.ski_area and Activity.objects.filter(user=activity.user, ski_area=activity.ski_area, start_time__lt=activity.start_time).count() == 0:
        badge, _ = get_or_create_badge_by_natural_key('FIRST_SKI_AREA')
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

        # Clean up: remove this badge from any later activities in the same ski area
        # (handles case where earlier activity gets synced after later ones)
        later_activities_same_area = Activity.objects.filter(
            user=activity.user,
            ski_area=activity.ski_area,
            start_time__gt=activity.start_time
        )
        ActivityBadge.objects.filter(
            badge=badge,
            activity__in=later_activities_same_area
        ).delete()

    # x days in a row in a ski area
    i = 1
    while Activity.objects.filter(user=activity.user, ski_area=activity.ski_area, start_time__date=activity.start_time.date() - timedelta(days=i)).exists():
        i += 1
    if i > 1:
        natural_key, config = get_streak_badge_config(i, ski_area_specific=True)
        badge, _ = get_or_create_badge_by_natural_key(natural_key, **config)
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

    # x days in a row
    i = 1
    while Activity.objects.filter(user=activity.user, start_time__date=activity.start_time.date() - timedelta(days=i)).exists():
        i += 1
    if i > 1:
        natural_key, config = get_streak_badge_config(i, ski_area_specific=False)
        badge, _ = get_or_create_badge_by_natural_key(natural_key, **config)
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

    # Completeness and lift variety badges
    if activity.ski_area:
        from .utils.completeness import calculate_activity_completeness, calculate_ski_area_completeness

        # Daily completeness badges
        daily_completeness = calculate_activity_completeness(activity)
        daily_percentage = daily_completeness['daily_completion_percentage']

        if daily_percentage >= 100:
            badge, _ = get_or_create_badge_by_natural_key('DAILY_COMPLETENESS_100')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
        elif daily_percentage >= 75:
            badge, _ = get_or_create_badge_by_natural_key('DAILY_COMPLETENESS_75')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
        elif daily_percentage >= 50:
            badge, _ = get_or_create_badge_by_natural_key('DAILY_COMPLETENESS_50')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
        elif daily_percentage >= 25:
            badge, _ = get_or_create_badge_by_natural_key('DAILY_COMPLETENESS_25')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

        # Lift variety badges
        unique_lifts_today = daily_completeness['lifts_used_today']
        if unique_lifts_today >= 30:
            badge, _ = get_or_create_badge_by_natural_key('LIFT_VARIETY_30')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
        elif unique_lifts_today >= 20:
            badge, _ = get_or_create_badge_by_natural_key('LIFT_VARIETY_20')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
        elif unique_lifts_today >= 15:
            badge, _ = get_or_create_badge_by_natural_key('LIFT_VARIETY_15')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
        elif unique_lifts_today >= 10:
            badge, _ = get_or_create_badge_by_natural_key('LIFT_VARIETY_10')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
        elif unique_lifts_today >= 5:
            badge, _ = get_or_create_badge_by_natural_key('LIFT_VARIETY_5')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})

        # Overall completeness badges (check current state after this activity)
        overall_completeness = calculate_ski_area_completeness(activity.user, activity.ski_area)
        completion_percentage = overall_completeness['completion_percentage']

        if completion_percentage >= 100:
            badge, _ = get_or_create_badge_by_natural_key('COMPLETENESS_100')
            # Award to the activity that achieved 100% completion
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
            # Remove from any earlier activities in the same ski area
            ActivityBadge.objects.filter(
                badge=badge,
                activity__user=activity.user,
                activity__ski_area=activity.ski_area,
                activity__start_time__lt=activity.start_time
            ).delete()
        elif completion_percentage >= 75:
            badge, _ = get_or_create_badge_by_natural_key('COMPLETENESS_75')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
            # Remove from later activities that might have gotten it prematurely
            ActivityBadge.objects.filter(
                badge=badge,
                activity__user=activity.user,
                activity__ski_area=activity.ski_area,
                activity__start_time__gt=activity.start_time
            ).delete()
        elif completion_percentage >= 50:
            badge, _ = get_or_create_badge_by_natural_key('COMPLETENESS_50')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
            ActivityBadge.objects.filter(
                badge=badge,
                activity__user=activity.user,
                activity__ski_area=activity.ski_area,
                activity__start_time__gt=activity.start_time
            ).delete()
        elif completion_percentage >= 25:
            badge, _ = get_or_create_badge_by_natural_key('COMPLETENESS_25')
            ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on': activity.start_time})
            ActivityBadge.objects.filter(
                badge=badge,
                activity__user=activity.user,
                activity__ski_area=activity.ski_area,
                activity__start_time__gt=activity.start_time
            ).delete()


def reassign_all_badges(user=None):
    """
    Reassign all badges for all activities. Uses assign_badges which is rerunnable.

    Args:
        user: If specified, only reassign badges for this user. If None, reassign for all users.

    Returns:
        dict: Statistics about the reassignment process
    """
    from django.contrib.auth import get_user_model
    import logging

    logger = logging.getLogger(__name__)
    User = get_user_model()

    if user:
        users = [user]
    else:
        # Get all users who have activities
        users = User.objects.filter(activity__isnull=False).distinct()

    total_activities = 0
    badges_before = ActivityBadge.objects.count()

    logger.info(f"Starting badge reassignment for {len(users)} users")

    for user_obj in users:
        # Get all activities for this user, ordered by start_time to ensure proper badge assignment
        activities = Activity.objects.filter(user=user_obj).order_by('start_time')

        logger.info(f"Processing {activities.count()} activities for user {user_obj.username}")

        for activity in activities:
            assign_badges(activity)
            total_activities += 1

    badges_after = ActivityBadge.objects.count()

    result = {
        'users_processed': len(users),
        'activities_processed': total_activities,
        'badges_before': badges_before,
        'badges_after': badges_after,
        'badges_added': badges_after - badges_before
    }

    logger.info(f"Badge reassignment complete: {result}")
    return result