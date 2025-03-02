from django import forms
from djmoney.forms.fields import MoneyField
from djmoney.forms.widgets import MoneyWidget
from dal import autocomplete
from activities.models import Activity
from osm.models import SkiArea, SkiAreaNetwork
from .models import SeasonPass
import datetime

this_year = datetime.date.today().year
years = range(this_year-5, this_year+5)

class CostForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ['cost']


class SeasonPassForm(forms.ModelForm):
    skiarea = forms.ModelChoiceField(
        queryset=SkiArea.objects.all(),
        label="Ski Area",
        widget=autocomplete.ModelSelect2(
            url='skiarea-autocomplete',  # The URL name of the autocomplete view
            attrs={"class": "form-control", "data-placeholder": "Search for a ski area..."}
        )
    , required=False
    )    
    skiarea_network = forms.ModelChoiceField(
        queryset=SkiAreaNetwork.objects.all(),
        label="Ski Area Network",
        widget=forms.Select(attrs={"class": "form-control"})
    , required=False)
    price = MoneyField(label="Price", max_digits=6, decimal_places=2, default_currency='CHF', widget=MoneyWidget(attrs={"class": "form-control"}))
    valid_from = forms.DateField(
        label="Valid From", 
        widget=forms.SelectDateWidget(years=years, attrs={"class": "form-control"}),
        initial=datetime.date.today()
        )
    valid_until = forms.DateField(
        label="Valid Until", 
        widget=forms.SelectDateWidget(years=years, attrs={"class": "form-control"}),
        initial=datetime.date.today()
        )

    class Meta:
        model = SeasonPass
        fields = ["skiarea", "skiarea_network", "price", "valid_from", "valid_until"]
