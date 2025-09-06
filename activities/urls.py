from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('admin/', views.sync_strava_admin, name="sync_strava_admin"),
    path("", views.activity_list, name="activity_list"),
    path("<int:activity_id>/", views.activity_detail, name="activity_detail"),
    path("<int:activity_id>/reprocess/", views.reprocess_activity, name="reprocess_activity"),
    path("strava/<strava_id>/", views.activity_detail_strava, name="activity_detail_strava"),
    path("skiarea/<int:skiarea_id>/", views.activity_list_skiarea_detail, name="skiarea_detail"),
    path("skiarea/<int:skiarea_id>/<str:season>", views.activity_list_skiarea_detail, name="skiarea_detail_season"),    
    path("skiarea/", views.activity_list_skiarea, name="activity_list_skiarea"),
    path("skiarea/<str:season>", views.activity_list_skiarea, name="activity_list_skiarea_season"),
    path("sync_strava_all/", views.sync_strava_all, name="sync_strava_all"),
    path("sync_strava/", views.sync_strava, name="sync_strava"),
    path("reprocess_all/", views.sync_reprocess_all, name="reprocess_all"),
    path("reset_all", views.reset_all, name="reset_all"),
    path("liftrides", views.lift_ride_list_season, name="lift_ride_list"),
    path("liftrides/all-seasons/", views.lift_ride_list_season, name="lift_ride_list_season_all"),
    path("liftrides/all/", views.lift_ride_list, name="lift_ride_list_all"),
    path("liftrides/<int:year>/", views.lift_ride_list, name="lift_ride_list_year"),
    path("liftrides/<str:season>", views.lift_ride_list_season, name="lift_ride_list_season"),
    path("map/<int:activity_id>/", views.segment_map, name="activity_map"),
    path("strava/webhook/", views.strava_webhook, name="strava_webhook"),
    path("strava/webhook/subscribe/", views.subscribe_strava_webhook, name="strava_webhook_subscribe"),
]