from django.urls import path
from .views.trips import trip_list, trip_detail, rename_trip, recluster_trips

urlpatterns = [
    path('', trip_list, name='trip_list'),
    path('<int:trip_id>/', trip_detail, name='trip_detail'),
    path('<int:trip_id>/rename/', rename_trip, name='rename_trip'),
    path('recluster/', recluster_trips, name='recluster_trips'),
]
