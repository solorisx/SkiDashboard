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


urlpatterns = [
    path('', views.home, name="home"),
    path('', include('activities.urls')),
    path('init_networks/', views.initialize_ski_area_networks, name="init_networks"),    
    path('admin/', admin.site.urls),
    path('hello/', views.hello_world),
    path('home/', views.home, name="home"),
    path('accounts/', include('allauth.urls')),
    path("activities/", views.activity_list, name="activity_list"),
    path("activities/<int:activity_id>/", views.activity_detail, name="activity_detail"),
    path("activities/<int:activity_id>/reprocess/", views.reprocess_activity, name="reprocess_activity"),
    path("activities/skiarea/<int:skiarea_id>/", views.activity_list_skiarea_detail, name="skiarea_detail"),
    path("activities/skiarea/<int:skiarea_id>/<str:season>", views.activity_list_skiarea_detail, name="skiarea_detail_season"),    
    path("activities/skiarea/", views.activity_list_skiarea, name="activity_list_skiarea"),
    path("activities/skiarea/<str:season>", views.activity_list_skiarea, name="activity_list_skiarea_season"),
    path("sync_strava_all/", views.sync_strava_all, name="sync_strava_all"),
    path("sync_strava/", views.sync_strava, name="sync_strava"),
    path("reprocess_all/", views.sync_reprocess_all, name="reprocess_all"),
    path("reset_all", views.reset_all, name="reset_all"),
    path("liftrides", views.lift_ride_list_season, name="lift_ride_list"),
    path("liftrides/all-seasons/", views.lift_ride_list_season, name="lift_ride_list_season_all"),
    path("liftrides/all/", views.lift_ride_list, name="lift_ride_list_all"),
    path("liftrides/<int:year>/", views.lift_ride_list, name="lift_ride_list_year"),
    path("liftrides/<str:season>", views.lift_ride_list_season, name="lift_ride_list_season"),
]
