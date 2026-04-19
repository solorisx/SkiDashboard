"""
URL configuration for SkiingDashboard project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from . import views
import os


urlpatterns = [
    path('', views.landing, name="landing"),
    path('activities/', include('activities.urls')),
    path('trips/', include('activities.trips_urls')),
    path('init_networks/', views.initialize_ski_area_networks, name="init_networks"),
    path('admin/', admin.site.urls),
    path('home/', views.home, name="home"),
    # Custom Strava OAuth URLs must come BEFORE allauth.urls
    path('accounts/strava/login/', include('core.strava_urls')),
    path('accounts/', include('allauth.urls')),
    path('accounts/delete/', views.UserDeleteView.as_view(), name='account_delete'),
    path('accounts/profile/', views.profile_management, name='profile_management'),
    path("accounts/strava/connection/", views.strava_connection_view, name="strava-connection"),
    path("accounts/strava/unlink/", views.strava_unlink_view, name="strava-unlink"),
    path('cost/', include('cost.urls')),
    path("osm/", include('osm.urls')),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("terms/", views.terms_of_service, name="terms_of_service"),
    path("premium/", views.premium_info, name="premium_info"),
    path("webhooks/buymeacoffee/", views.buymeacoffee_webhook, name="buymeacoffee_webhook"),
    path("admin/membership/", views.membership_admin, name="membership_admin"),

    path("api/season-stats/", views.season_stats_api, name="season_stats_api"),
    path("api/lift-ride/", views.lift_ride_api, name="lift_ride_api"),
    path("api/lift-ride/<int:lift_ride_id>/", views.lift_ride_api, name="lift_ride_api"),
    path("api/piste-ride/<int:piste_ride_id>/", views.piste_ride_api, name="piste_ride_api"),
    path("api/season-pass/", views.SeasonPassAPI.as_view(), name="season_pass_api"),
    path("api/season-pass/<int:season_pass_id>/", views.SeasonPassAPI.as_view(), name="season_pass_api"),
]

if os.getenv("ENABLE_SILK", "false").lower() == "true":
    urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]
