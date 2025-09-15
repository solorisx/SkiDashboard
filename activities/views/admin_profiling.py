"""
Admin profiling views for activity parsing performance monitoring.
"""
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Max, Min, Sum, Count, Q
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
from activities.models import Activity, ActivityParserProfile


@staff_member_required
def activity_profiling_dashboard(request):
    """
    Admin-only view showing recent parsed activities with their profiling data.
    """
    # Get filter parameters
    days = int(request.GET.get('days', 7))
    page = request.GET.get('page', 1)

    # Filter activities from the last N days that have profiling data
    cutoff_date = timezone.now() - timedelta(days=days)

    # Get recent activities with their profiling data
    activities = Activity.objects.filter(
        processed_on__gte=cutoff_date,
        parser_profiles__isnull=False
    ).select_related('user', 'ski_area').prefetch_related('parser_profiles').distinct().order_by('-processed_on')

    # Paginate results
    paginator = Paginator(activities, 20)
    page_obj = paginator.get_page(page)

    # Get aggregated performance statistics for the period
    profiles_queryset = ActivityParserProfile.objects.filter(
        activity__processed_on__gte=cutoff_date
    )

    # Calculate period stats manually to avoid aggregate conflicts
    period_stats = {
        'total_operations': profiles_queryset.count(),
        'total_processing_time': 0,
        'max_total_time': 0,
        'avg_total_time': 0
    }

    if period_stats['total_operations'] > 0:
        # Calculate totals manually
        total_sum = 0
        max_time = 0
        for profile in profiles_queryset.values('total_time'):
            total_sum += profile['total_time']
            if profile['total_time'] > max_time:
                max_time = profile['total_time']

        period_stats['total_processing_time'] = total_sum
        period_stats['max_total_time'] = max_time
        period_stats['avg_total_time'] = total_sum / period_stats['total_operations']

    # Get top slow operations - calculate manually to avoid aggregate issues
    operations_data = {}
    for profile in profiles_queryset.values('operation', 'total_time', 'call_count', 'activity'):
        op_name = profile['operation']
        if op_name not in operations_data:
            operations_data[op_name] = {
                'operation': op_name,
                'total_time': 0,
                'max_time': 0,
                'call_count': 0,
                'activity_ids': set(),
                'operation_count': 0
            }

        operations_data[op_name]['total_time'] += profile['total_time']
        operations_data[op_name]['call_count'] += profile['call_count']
        operations_data[op_name]['activity_ids'].add(profile['activity'])
        operations_data[op_name]['operation_count'] += 1

        if profile['total_time'] > operations_data[op_name]['max_time']:
            operations_data[op_name]['max_time'] = profile['total_time']

    # Convert to list and calculate averages
    slow_operations = []
    for op_data in operations_data.values():
        op_data['activity_count'] = len(op_data['activity_ids'])
        if op_data['operation_count'] > 0:
            op_data['avg_time'] = op_data['total_time'] / op_data['operation_count']
        else:
            op_data['avg_time'] = 0
        del op_data['activity_ids']  # Remove set for template compatibility
        slow_operations.append(op_data)

    # Sort by average time and take top 10
    slow_operations = sorted(slow_operations, key=lambda x: x['avg_time'], reverse=True)[:10]

    # Get activities with longest processing times
    slowest_activities = Activity.objects.filter(
        processed_on__gte=cutoff_date,
        processing_time__isnull=False
    ).order_by('-processing_time')[:10]

    context = {
        'page_obj': page_obj,
        'activities': page_obj.object_list,
        'period_stats': period_stats,
        'slow_operations': slow_operations,
        'slowest_activities': slowest_activities,
        'days': days,
        'cutoff_date': cutoff_date,
    }

    return render(request, 'admin/activity_profiling_dashboard.html', context)


@staff_member_required
def activity_profiling_detail(request, activity_id):
    """
    Detailed profiling view for a specific activity.
    """
    activity = Activity.objects.select_related('user', 'ski_area').get(id=activity_id)

    # Get all profiling data for this activity
    profiles = ActivityParserProfile.objects.filter(activity=activity, version=activity.version).order_by('-total_time')
    profiles_list = list(profiles)

    # Calculate summary statistics manually to avoid aggregate conflicts
    summary_stats = {
        'total_operations': profiles.count(),
        'total_time': 0,
        'max_time': 0,
        'min_time': float('inf'),
        'total_calls': 0,
        'avg_time': 0
    }

    if summary_stats['total_operations'] > 0:
        for profile in profiles.values('total_time', 'call_count'):
            summary_stats['total_time'] += profile['total_time']
            summary_stats['total_calls'] += profile['call_count']

            if profile['total_time'] > summary_stats['max_time']:
                summary_stats['max_time'] = profile['total_time']

            if profile['total_time'] < summary_stats['min_time']:
                summary_stats['min_time'] = profile['total_time']

        summary_stats['avg_time'] = summary_stats['total_time'] / summary_stats['total_operations']

        # Handle case where no profiles exist
        if summary_stats['min_time'] == float('inf'):
            summary_stats['min_time'] = 0

        # Calculate percentage for each profile
        for profile in profiles_list:
            if summary_stats['total_time'] > 0:
                profile.percentage = (profile.total_time / summary_stats['total_time']) * 100
            else:
                profile.percentage = 0

    context = {
        'activity': activity,
        'profiles': profiles_list,
        'summary_stats': summary_stats,
    }

    return render(request, 'admin/activity_profiling_detail.html', context)