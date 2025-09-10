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
    path('init_networks/', views.initialize_ski_area_networks, name="init_networks"),    
    path('admin/', admin.site.urls),
    path('home/', views.home, name="home"),
    path('accounts/', include('allauth.urls')),
    path('accounts/delete/', views.UserDeleteView.as_view(), name='account_delete'),
    path("accounts/strava/", views.strava_connection_view, name="strava-connection"),
    path("accounts/strava/unlink/", views.strava_unlink_view, name="strava-unlink"),
    path('cost/', include('cost.urls')),
    path("osm/", include('osm.urls')),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("terms/", views.terms_of_service, name="terms_of_service"),

    path("api/season-stats/", views.season_stats_api, name="season_stats_api"),
    path("api/lift-ride/", views.lift_ride_api, name="lift_ride_api"),
    path("api/lift-ride/<int:lift_ride_id>/", views.lift_ride_api, name="lift_ride_api"),
    path("api/season-pass/", views.SeasonPassAPI.as_view(), name="season_pass_api"),
    path("api/season-pass/<int:season_pass_id>/", views.SeasonPassAPI.as_view(), name="season_pass_api"),
]

if os.getenv("ENABLE_SILK", "false").lower() == "true":
    urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]
