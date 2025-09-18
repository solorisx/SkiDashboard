from django import forms
from .models import UserProfile
from osm.models import LiftFilterConfig

import logging

logger = logging.getLogger(__name__)

class UserDeleteForm(forms.Form):
    confirm = forms.CharField(
        help_text='Type DELETE to confirm.',
        widget=forms.TextInput(attrs={'autocomplete': 'off'})
    )

    def clean_confirm(self):
        v = self.cleaned_data['confirm'].strip().upper()
        if v != "DELETE":
            raise forms.ValidationError("Type DELETE to confirm.")
        return v


class UserProfileForm(forms.ModelForm):
    excluded_lift_types = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select lift types to exclude from your statistics"
    )

    class Meta:
        model = UserProfile
        fields = [
            # 'language', 'timezone', 'metric_units', 'dark_mode',
            'excluded_lift_types', 'season_start_month', 'season_start_day'
        ]
        widgets = {
            #'language': forms.Select(attrs={'class': 'form-select'}),
            #'timezone': forms.Select(attrs={'class': 'form-select'}),
            #'metric_units': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            #'dark_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'season_start_month': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'season_start_day': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Get popular lift types for choices
        popular_lift_types = LiftFilterConfig.get_popular_lift_types()
        logger.debug(f"Popular lift types: {popular_lift_types}")
        self.fields['excluded_lift_types'].choices = [
            (lift_type, lift_type_name)
            for lift_type, lift_type_name in popular_lift_types
        ]

        # Set initial value from JSONField
        if self.instance and self.instance.pk:
            self.fields['excluded_lift_types'].initial = self.instance.excluded_lift_types or []

    def save(self, commit=True):
        logger.debug("Saving UserProfileForm with cleaned_data: %s", self.cleaned_data)
        instance = super().save(commit=False)
        # Convert excluded_lift_types to list for JSONField
        instance.excluded_lift_types = self.cleaned_data.get('excluded_lift_types', [])
        logger.debug("commit=%s, excluded_lift_types=%s", commit, instance.excluded_lift_types)
        if commit:
            instance.save()
        return instance