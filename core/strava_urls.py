"""Custom Strava OAuth URLs with dynamic scope support."""
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2CallbackView,
    OAuth2LoginView,
)
from django.urls import path
from core.strava_adapter import CustomStravaOAuth2Adapter
import logging


logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info("LOADING core.strava_urls module")
logger.info("=" * 80)


# Create view instances using our custom adapter
oauth2_login = OAuth2LoginView.adapter_view(CustomStravaOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(CustomStravaOAuth2Adapter)

logger.info(f"Created oauth2_login view: {oauth2_login}")
logger.info(f"Created oauth2_callback view: {oauth2_callback}")


urlpatterns = [
    path("", oauth2_login, name="strava_login"),
    path("callback/", oauth2_callback, name="strava_callback"),
]
