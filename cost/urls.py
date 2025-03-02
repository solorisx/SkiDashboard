from django.contrib import admin
from django.urls import include, path
from . import views
from osm.views import SkiAreaAutocomplete


urlpatterns = [
    path('', views.home),
    path('home/', views.home, name="home"),
    path('season_pass_detail/<int:pass_id>/', views.season_pass_detail, name="season_pass_detail"),
    path('delete_season_pass/<int:pass_id>/', views.delete_season_pass, name="delete_season_pass"),
    path('skiarea-autocomplete/', SkiAreaAutocomplete.as_view(), name='skiarea-autocomplete2'),
    path('home/skiarea-autocomplete/', SkiAreaAutocomplete.as_view(), name='skiarea-autocomplete3'),
]