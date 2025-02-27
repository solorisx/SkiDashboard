from django import forms

class OSMSyncForm(forms.Form):
    osm_id = forms.CharField(label="OSM ID", widget=forms.TextInput(attrs={"class": "form-control"}))
    osm_type = forms.ChoiceField(
        choices=[("Relation", "Relation"), ("Area", "Area")],
        label="OSM Type",
        widget=forms.Select(attrs={"class": "form-control"})
    )

class OSMFileSyncForm(forms.Form):
    sync_ways = forms.BooleanField(label="Sync Ways", required=False)
    sync_relations = forms.BooleanField(label="Sync Relations", required=False)
    sync_nodes = forms.BooleanField(label="Sync Nodes", required=False)
    sync_areas = forms.BooleanField(label="Sync Areas", required=False)
