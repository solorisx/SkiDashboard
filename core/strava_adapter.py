"""Custom Strava provider adapter with dynamic scope support."""
import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.strava.provider import StravaProvider
from allauth.socialaccount.providers.strava.views import StravaOAuth2Adapter


logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info("LOADING core.strava_adapter module")
logger.info("=" * 80)


class CustomStravaProvider(StravaProvider):
    """Custom Strava provider with dynamic scopes."""
    id = 'strava'

    def get_default_scope(self):
        """Return default scopes - will be overridden by adapter."""
        logger.debug("CustomStravaProvider.get_default_scope called")
        return ['read', 'activity:read']

    def get_scope(self):
        """Override to return dynamic scopes based on user preferences as comma-separated string."""
        logger.debug("CustomStravaProvider.get_scope called")
        # The provider has self.request available from __init__
        scopes = get_dynamic_strava_scope(self.request)
        # Return as comma-separated string for Strava (not a list!)
        scope_str = ','.join(scopes)
        logger.info(f"CustomStravaProvider.get_scope returning string: {scope_str}")
        return [scope_str]

    def get_scope_delimiter(self):
        """Override to use comma instead of space for Strava."""
        logger.debug("CustomStravaProvider.get_scope_delimiter called - returning comma")
        return ','


class CustomStravaOAuth2Adapter(StravaOAuth2Adapter):
    """Custom OAuth2 adapter for Strava with dynamic scopes."""

    def get_provider(self):
        """Return custom provider instance."""
        # Get the app from the parent class method
        provider = super().get_provider()
        # Return our custom provider with the same request and app
        return CustomStravaProvider(self.request, app=provider.app)

    def get_scope_delimiter(self):
        """Override to use comma instead of space for Strava."""
        logger.debug("CustomStravaOAuth2Adapter.get_scope_delimiter called - returning comma")
        return ','

    def get_auth_params(self, request, action):
        """Override auth params to set comma-separated scopes."""
        logger.debug("=" * 80)
        logger.debug("CustomStravaOAuth2Adapter.get_auth_params called!")

        params = super().get_auth_params(request, action)

        logger.debug(f"Params from super: {params}")

        # Get dynamic scopes
        scopes = get_dynamic_strava_scope(request)
        scope_str = ','.join(scopes)

        logger.debug(f"Dynamic scopes: {scopes}")
        logger.debug(f"Scope string: {scope_str}")

        # Override scope
        params['scope'] = scope_str

        logger.debug(f"Final params: {params}")
        logger.debug("=" * 80)

        return params


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter that modifies Strava scopes based on user preferences.
    """

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        """
        Handle authentication errors.
        """
        logger.error(f"Strava authentication error: provider={provider_id}, error={error}, exception={exception}, extra={extra_context}")
        return super().authentication_error(request, provider_id, error, exception, extra_context)

    def pre_social_login(self, request, sociallogin):
        """
        Called after successful social login, before the login is processed.
        Clear reauth flags if present.
        """
        super().pre_social_login(request, sociallogin)

        # Clear reauth session flags after successful reauth
        if sociallogin.account.provider == 'strava':
            if 'strava_reauth_needed' in request.session:
                del request.session['strava_reauth_needed']
                logger.info("Cleared strava_reauth_needed flag")
            if 'strava_reauth_write_scope' in request.session:
                del request.session['strava_reauth_write_scope']
                logger.info("Cleared strava_reauth_write_scope flag")


def get_dynamic_strava_scope(request):
    """
    Determine Strava scope dynamically based on user preferences.
    Returns a list of scopes (NOT a string).
    """
    # Base scopes that are always required
    scopes = ['read', 'activity:read']

    # Check if user has a profile with write access preference
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        try:
            from core.models import UserProfile
            profile = UserProfile.objects.get(user=request.user)
            if profile.opt_in_strava_write:
                scopes.append('activity:write')
                logger.info(f"Adding activity:write scope for user {request.user.username}")
        except UserProfile.DoesNotExist:
            logger.debug("No profile found for user")
        except Exception as e:
            logger.warning(f"Could not check user profile for Strava scopes: {e}")

    # Also check session for reauth scenario
    if request and hasattr(request, 'session'):
        if request.session.get('strava_reauth_write_scope', False):
            if 'activity:write' not in scopes:
                scopes.append('activity:write')
            logger.info("Adding activity:write scope from session reauth flag")

    logger.info(f"Strava scopes (list): {scopes}")
    return scopes
