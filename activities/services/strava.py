"""Strava service for handling Strava-related operations."""

import logging
from allauth.socialaccount.models import SocialAccount

logger = logging.getLogger(__name__)


class StravaService:
    """Service for Strava-related operations."""
    
    @staticmethod
    def validate_user_has_strava_account(user):
        """Check if user has a connected Strava account."""
        return SocialAccount.objects.filter(user=user, provider="strava").exists()
    
    @staticmethod
    def get_user_by_strava_id(strava_user_id):
        """Get Django user by their Strava ID."""
        from django.contrib.auth import get_user_model
        
        try:
            return get_user_model().objects.get(
                socialaccount__uid=strava_user_id,
                socialaccount__provider="strava"
            )
        except get_user_model().DoesNotExist:
            logger.error(f"No user found for Strava ID {strava_user_id}")
            return None