import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger(__name__)


def grant_premium(user, source, granted_by=None):
    """Grant 1 year of premium to a user. Resets notification flags so reminders fire again."""
    profile = user.userprofile
    profile.is_premium = True
    profile.premium_expires_at = timezone.now() + timedelta(days=365)
    profile.premium_granted_at = timezone.now()
    profile.premium_payment_source = source
    profile.premium_granted_by = granted_by
    profile.premium_expiry_30d_notified = False
    profile.premium_expiry_7d_notified = False
    profile.save(update_fields=[
        'is_premium', 'premium_expires_at', 'premium_granted_at',
        'premium_payment_source', 'premium_granted_by',
        'premium_expiry_30d_notified', 'premium_expiry_7d_notified',
    ])
    logger.info(f"Granted premium to {user.email} via {source}, expires {profile.premium_expires_at}")


def revoke_premium(user):
    """Revoke premium membership immediately."""
    profile = user.userprofile
    profile.is_premium = False
    profile.premium_expires_at = None
    profile.save(update_fields=['is_premium', 'premium_expires_at'])
    logger.info(f"Revoked premium for {user.email}")


def get_current_season_label(user):
    """Return current season label e.g. '2025-2026'."""
    from activities.utils.seasons import get_season_dates
    start, _ = get_season_dates(current=True, user=user)
    return f"{start.year}-{start.year + 1}"


def filter_seasons_for_user(seasons, user):
    """Return only seasons the user may view. Free users see current season only."""
    try:
        if user.userprofile.is_premium_active():
            return seasons
    except Exception:
        pass
    current = get_current_season_label(user)
    return [s for s in seasons if s == current]


def premium_season_required(view_func):
    """Decorator: redirect free users away from past-season views."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        season = kwargs.get('season')
        if season and request.user.is_authenticated:
            try:
                is_premium = request.user.userprofile.is_premium_active()
            except Exception:
                is_premium = False
            if not is_premium:
                current = get_current_season_label(request.user)
                if season != current:
                    messages.warning(request, "Upgrade to Premium to view past seasons.")
                    return redirect('premium_info')
        return view_func(request, *args, **kwargs)
    return wrapped
