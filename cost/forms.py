from django import forms
from djmoney.forms.fields import MoneyField
from activities.models import Activity

class CostForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ['cost']