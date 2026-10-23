from django import forms
from djmoney.forms.fields import MoneyField as MoneyFormField
from djmoney.forms.widgets import MoneyWidget
from dal import autocomplete
from activities.models import Activity
from osm.models import SkiArea
import datetime

this_year = datetime.date.today().year
years = range(this_year-5, this_year+5)

class CostForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ['cost']

class SeasonPassForm(forms.Form):
    skiareaAdd = forms.ModelChoiceField(
        queryset=SkiArea.objects.all(),
        required=False,
        label="Ski Area",
        widget=autocomplete.ModelSelect2(
            url="skiarea-autocomplete",
            attrs={
                "data-placeholder": "Search for a ski area…",
                "data-width": "100%",
                "data-dropdown-parent": "#addSeasonPassModal",
                "data-theme": "bootstrap-5",
            },
        ),
    )
    skiareaEdit = forms.ModelChoiceField(
        queryset=SkiArea.objects.all(),
        required=False,
        label="Ski Area",
        widget=autocomplete.ModelSelect2(
            url="skiarea-autocomplete",
            attrs={
                "data-placeholder": "Search for a ski area…",
                "data-width": "100%",
                "data-dropdown-parent": "#editSeasonPassModal",
                "data-theme": "bootstrap-5",
            },
        ),
    )

    priceAdd = MoneyFormField(
        label="Price",
        max_digits=6,
        decimal_places=2,
        default_currency="CHF",
        widget=MoneyWidget(
            attrs={"class": "form-control"}
            ),
    )
    priceEdit = MoneyFormField(
        label="Price",
        max_digits=6,
        decimal_places=2,
        default_currency="CHF",
        widget=MoneyWidget(
            attrs={"class": "form-control"}
            ),
    )
