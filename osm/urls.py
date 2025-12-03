from django.contrib import admin
from django.urls import path
from . import views
from .views import SkiAreaAutocomplete

urlpatterns = [
    path('admin/', views.sync_osm, name='sync_osm'),
    path('admin/sync-osm-api/', views.sync_osm_api, name='sync-osm-api'),
    path('admin/sync-osm-file/', views.sync_osm_file, name='sync-osm-file'),
    path('admin/assign_network/', views.assign_skiarea_network, name='assign_network'),
    path('admin/update_segments/', views.update_segments, name='update_segments'),
    path('admin/update_piste_geometry/', views.update_piste_geometry, name='update_piste_geometry'),
    path('admin/upload_skiarea_networks/', views.SkiAreaNetworkUploadView.as_view(), name='skiarea_network_upload'),
    path('skiarea-autocomplete/', SkiAreaAutocomplete.as_view(), name='skiarea-autocomplete'),
    path('map/<int:osm_id>/', views.map, name='map'),
    path('segment-map/<int:osm_id>', views.segment_map, name='segment_map'),
]