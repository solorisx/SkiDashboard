from django.contrib import admin
from django.urls import path
from . import views
from .views import SkiAreaAutocomplete

urlpatterns = [
    path('admin/', views.sync_osm, name='sync_osm'),
    path('admin/sync-osm-api/', views.sync_osm_api, name='sync-osm-api'),
    path('admin/sync-osm-file/', views.sync_osm_file, name='sync-osm-file'),
    path('admin/assign_network/', views.assign_skiarea_network, name='assign_network'),
    path('skiarea-autocomplete/', SkiAreaAutocomplete.as_view(), name='skiarea-autocomplete',
),
]