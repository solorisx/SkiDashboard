import json
import logging
from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, F, Max, Sum
from django.db.models.functions import Round, TruncMonth
from django.shortcuts import render

from ..models import ActivityBadge
from ..utils.queries import get_filter_query, get_user_activities_base_query
from ..utils.seasons import get_seasons, get_season_dates, parse_season_string
from core.premium import filter_seasons_for_user, premium_season_required

logger = logging.getLogger(__name__)


@login_required
@premium_season_required
def activity_insights(request, season=None):
    """Show comprehensive insights dashboard for user's activities."""

    is_all_seasons = not season
    if is_all_seasons:
        season_start, season_end = get_season_dates(current=True, user=request.user)
        activities = get_user_activities_base_query(request.user)
    else:
        season_start, season_end = parse_season_string(season, user=request.user)
        filter_query = get_filter_query(request, season)
        activities = get_user_activities_base_query(request.user).filter(filter_query)
    seasons = filter_seasons_for_user(get_seasons(user=request.user), request.user)

    # Most recent activities (top 5)
    recent_activities = activities.annotate(
        total_distance_km=Round(F("total_distance")/1000, 2)
    ).order_by("-timestamp")[:5]

    # Activity with most vertical (total_descent)
    activity_most_vertical = activities.aggregate(
        max_descent=Max('total_descent')
    )
    most_vertical_activity = None
    if activity_most_vertical['max_descent']:
        most_vertical_activity = activities.annotate(
            total_distance_km=Round(F("total_distance")/1000, 2)
        ).filter(total_descent=activity_most_vertical['max_descent']).first()

    # Activity with most lift rides
    activity_most_lifts = activities.aggregate(
        max_lifts=Max('num_lift_rides')
    )
    most_lifts_activity = None
    if activity_most_lifts['max_lifts']:
        most_lifts_activity = activities.annotate(
            total_distance_km=Round(F("total_distance")/1000, 2)
        ).filter(num_lift_rides=activity_most_lifts['max_lifts']).first()

    # Badge statistics
    activity_badges = ActivityBadge.objects.filter(activity__in=activities)

    # Total badges count
    total_badges_count = activity_badges.count()

    # Unique badges with counts - ordered by rarity (legendary first) then by count
    unique_badges = activity_badges.values(
        'badge__natural_key',
        'badge__name',
        'badge__description',
        'badge__icon',
        'badge__rarity'
    ).annotate(
        count=Count('badge')
    ).order_by(
        # Custom ordering for rarity (legendary=0, platinum=1, gold=2, silver=3, bronze=4)
        models.Case(
            models.When(badge__rarity='legendary', then=0),
            models.When(badge__rarity='platinum', then=1),
            models.When(badge__rarity='gold', then=2),
            models.When(badge__rarity='silver', then=3),
            models.When(badge__rarity='bronze', then=4),
            default=5,
            output_field=models.IntegerField(),
        ),
        '-count'  # Then by count descending
    )

    # Badge rarity breakdown - ordered by rarity (legendary first)
    rarity_breakdown = activity_badges.values('badge__rarity').annotate(
        count=Count('badge')
    ).order_by(
        models.Case(
            models.When(badge__rarity='legendary', then=0),
            models.When(badge__rarity='platinum', then=1),
            models.When(badge__rarity='gold', then=2),
            models.When(badge__rarity='silver', then=3),
            models.When(badge__rarity='bronze', then=4),
            default=5,
            output_field=models.IntegerField(),
        )
    )

    # Create rarity mapping for display
    rarity_display = {}
    rarity_colors = {
        'bronze': '#cd7f32',
        'silver': '#c0c0c0',
        'gold': '#ffd700',
        'platinum': '#e5e4e2',
        'legendary': '#9400d3'
    }

    for rarity in rarity_breakdown:
        rarity_name = rarity['badge__rarity']
        rarity_display[rarity_name] = {
            'name': rarity_name.title(),
            'count': rarity['count'],
            'color': rarity_colors.get(rarity_name, '#6c757d')
        }

    # Overall statistics
    overall_stats = activities.aggregate(
        total_activities=Count('id'),
        total_distance_km=Round(Sum(F("total_distance"))/1000, 1),
        total_descent=Round(Sum('total_descent'), 0),
        total_lift_rides=Sum('num_lift_rides')
    )
    for key in overall_stats:
        if overall_stats[key] is None:
            overall_stats[key] = 0

    # Prior season stats for YoY comparison (skip for All Seasons view)
    prior_season_stats = None
    if not is_all_seasons:
        season_length = season_end - season_start
        prev_start = season_start - season_length
        prev_end = season_end - season_length
        try:
            prior_season_stats = get_user_activities_base_query(request.user).filter(
                timestamp__gte=prev_start,
                timestamp__lte=prev_end
            ).aggregate(
                total_activities=Count('id'),
                total_distance_km=Round(Sum(F("total_distance"))/1000, 1),
                total_descent=Round(Sum('total_descent'), 0),
                total_lift_rides=Sum('num_lift_rides')
            )
            for key in prior_season_stats:
                if prior_season_stats[key] is None:
                    prior_season_stats[key] = 0
        except Exception:
            prior_season_stats = None

    # Monthly breakdown for bar charts (activity count + descent by month)
    monthly_raw = (
        activities
        .annotate(month=TruncMonth('timestamp'))
        .values('month')
        .annotate(count=Count('id'), descent=Sum('total_descent'), lifts=Sum('num_lift_rides'))
        .order_by('month')
    )
    monthly_by_key = {
        row['month'].strftime('%b %Y'): row for row in monthly_raw if row['month']
    }

    # Build full month range; for all-seasons use the data's own span
    now = datetime.now()
    season_months = []
    if is_all_seasons and monthly_by_key:
        all_months = sorted(monthly_by_key.keys(), key=lambda m: datetime.strptime(m, '%b %Y'))
        first_month = datetime.strptime(all_months[0], '%b %Y')
        cur = date(first_month.year, first_month.month, 1)
        end_month = date(now.year, now.month, 1)
    else:
        cur = date(season_start.year, season_start.month, 1)
        end_cap = min(season_end, now)
        end_month = date(end_cap.year, end_cap.month, 1)
    while cur <= end_month:
        season_months.append(cur.strftime('%b %Y'))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    monthly_stats = [
        {
            'month': m,
            'count': monthly_by_key[m]['count'] if m in monthly_by_key else 0,
            'descent': round(monthly_by_key[m]['descent'] or 0) if m in monthly_by_key else 0,
            'lifts': monthly_by_key[m]['lifts'] if m in monthly_by_key else 0,
        }
        for m in season_months
    ]

    # Calendar heatmap data (date → descent) for the current view
    calendar_raw = activities.values('timestamp__date').annotate(descent=Sum('total_descent'))
    calendar_data = {
        str(row['timestamp__date']): round(row['descent'] or 0)
        for row in calendar_raw
    }

    context = {
        'recent_activities': recent_activities,
        'most_vertical_activity': most_vertical_activity,
        'most_lifts_activity': most_lifts_activity,
        'total_badges_count': total_badges_count,
        'unique_badges': unique_badges,
        'rarity_breakdown': rarity_display,
        'overall_stats': overall_stats,
        'prior_season_stats': prior_season_stats,
        'is_all_seasons': is_all_seasons,
        'monthly_stats': json.dumps(monthly_stats),
        'calendar_data': json.dumps(calendar_data),
        'seasons': seasons,
        'selected_season': season,
    }

    return render(request, 'activities/insights.html', context)