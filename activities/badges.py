from datetime import timedelta
from .models import Activity, Badge, ActivityBadge

def assign_badges(activity: Activity):

    # 5 rides in a day
    if activity.num_lift_rides >= 5:
        badge, _ = Badge.objects.get_or_create(name='5 lifts in a Day', defaults={'description': 'You rode 5 lifts in a single day!', 'icon': 'fa-solid fa-5'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})

    # 10 rides in a day
    if activity.num_lift_rides >= 10:
        badge, _ = Badge.objects.get_or_create(name='10 lifts in a Day', defaults={'description': 'You rode 10 lifts in a single day!', 'icon': 'fa-solid fa-x'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})

    # 20 rides in a day
    if activity.num_lift_rides >= 20:
        badge, _ = Badge.objects.get_or_create(name='20 lifts in a Day', defaults={'description': 'You rode 20 lifts in a single day!', 'icon': 'fa-solid fa-stopwatch-20'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})

    # 10'000hm in a day
    if activity.total_ascent >= 10000:
        badge, _ = Badge.objects.get_or_create(name='10\'000hm in a Day', defaults={'description': 'You climbed 10\'000m in a single day!', 'icon': 'fa-solid fa-mountain'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})

    # 20'000hm in a day
    if activity.total_ascent >= 20000:
        badge, _ = Badge.objects.get_or_create(name='20\'000hm in a Day', defaults={'description': 'You climbed 20\'000m in a single day!', 'icon': 'fa-solid fa-mountain-sun'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})
    
    # first day in a ski area
    if Activity.objects.filter(user=activity.user, ski_area=activity.ski_area, start_time__lt=activity.start_time).count() == 0:
        badge, _ = Badge.objects.get_or_create(name='First day in a Ski Area', defaults={'description': 'You visited a new ski area for the first time!', 'icon': 'fa-solid fa-1'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})
        ActivityBadge.objects.filter(badge=badge, activity__user=activity.user).exclude(activity=activity).delete()

    # x days in a row in a ski area
    i = 1
    while Activity.objects.filter(user=activity.user, ski_area=activity.ski_area, start_time__date=activity.start_time.date() - timedelta(days=i)).exists():
        i += 1
        badge, _ = Badge.objects.get_or_create(name=f'{i} days in a row in a Ski Area', defaults={'description': f'You visited the same ski area {i} days in a row!', 'icon': f'fa-solid fa-medal'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})

    # x days in a row
    i = 1
    while Activity.objects.filter(user=activity.user, start_time__date=activity.start_time.date() - timedelta(days=i)).exists():
        i += 1
        badge, _ = Badge.objects.get_or_create(name=f'{i} days in a row', defaults={'description': f'You skied {i} days in a row!', 'icon': f'fa-light fa-medal'})
        ActivityBadge.objects.get_or_create(activity=activity, badge=badge, defaults={'achieved_on':activity.start_time})