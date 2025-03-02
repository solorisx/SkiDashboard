from django import forms
from dal import autocomplete
from .models import SkiArea, SkiAreaNetwork
from django.db.models import Q

from datetime import datetime

this_year = datetime.now().year
years = range(this_year-5, this_year+5)

class OSMSyncForm(forms.Form):
    osm_id = forms.CharField(label="OSM ID", widget=forms.TextInput(attrs={"class": "form-control"}))
    osm_type = forms.ChoiceField(
        choices=[("Relation", "Relation"), ("Area", "Area"), ("Way", "Way"), ("Node", "Node")],
        label="OSM Type",
        widget=forms.Select(attrs={"class": "form-control"})
    )

class OSMFileSyncForm(forms.Form):
    sync_ways = forms.BooleanField(label="Sync Ways", required=False)
    sync_relations = forms.BooleanField(label="Sync Relations", required=False)
    sync_nodes = forms.BooleanField(label="Sync Nodes", required=False)
    sync_areas = forms.BooleanField(label="Sync Areas", required=False)


class SkiAreaNetworkForm(forms.Form):
    skiarea_network = forms.ModelChoiceField(
        queryset=SkiAreaNetwork.objects.all().order_by("name"),
        label="Ski Area Network",
        widget=forms.Select(attrs={"class": "form-control"})
        )
    skiarea = forms.ModelChoiceField(
        queryset=SkiArea.objects.filter(~Q(name__icontains="unnamed"), way__isnull=False).order_by("name"),
        label="Ski Area",
        widget=forms.Select(attrs={"class": "form-control"})
# widget=autocomplete.ModelSelect2(
# url='skiarea-autocomplete',
# attrs={"class": "form-control", "data-placeholder": "Search for a ski area..."}
# )
    )
    valid_from = forms.DateField(
        label="Valid From", 
        widget=forms.SelectDateWidget(years=years, attrs={"class": "form-control"}),
        initial=datetime.today()
        )
    valid_until = forms.DateField(
        label="Valid Until", 
        widget=forms.SelectDateWidget(years=years, attrs={"class": "form-control"}),
        initial=datetime.today()
        )