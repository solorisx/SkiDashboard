from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount
from dal import autocomplete

from .models import SummerActivity, SummerActivityType

User = get_user_model()

class StravaSyncForm(forms.Form):
    strava_activity_id = forms.CharField(
        label="Strava Activity ID",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        required=False,  # make optional so you can also just use 'all'
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(socialaccount__provider="strava").distinct(),
        label="User",
        widget=forms.Select(attrs={"class": "form-control"})
    )
    update = forms.BooleanField(
        label="Update Existing Activity",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

class PerUserSyncForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(socialaccount__provider="strava").distinct(),
        label="User",
        widget=forms.Select(attrs={"class": "form-control"})
    )
    all = forms.BooleanField(
        label="Sync ALL activities",
        required=False,
        help_text="Check to fetch all activities from Strava instead of only last 90 days. Overrides user setting.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )
    update = forms.BooleanField(
        label="Update Existing Activities",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

class GlobalSyncForm(forms.Form):
    """Empty form just to carry CSRF + submit."""
    pass

class BadgeReassignmentForm(forms.Form):
    """Form for reassigning badges."""
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(activity__isnull=False).distinct(),
        label="User (optional)",
        required=False,
        empty_label="All users",
        widget=forms.Select(attrs={"class": "form-control"})
    )


class SummerActivityForm(forms.ModelForm):
    """Create/edit a manually tracked summer activity.

    ``distance``/``duration`` are stored in metres/timedelta on the model but
    exposed in km/minutes here for friendlier manual entry.
    """

    distance_km = forms.DecimalField(
        required=False, min_value=0, label="Distance (km)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
    )
    duration_minutes = forms.IntegerField(
        required=False, min_value=0, label="Duration (minutes)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = SummerActivity
        fields = [
            'name', 'activity_type', 'date', 'ski_area', 'season_pass',
            'elevation_gain', 'strava_id', 'strava_type', 'cost', 'value', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'activity_type': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'season_pass': forms.Select(attrs={'class': 'form-select'}),
            'elevation_gain': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'strava_id': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Strava activity ID (optional)'}),
            'strava_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Hike, Ride'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'ski_area': autocomplete.ModelSelect2(
                url='skiarea-autocomplete',
                attrs={
                    'data-placeholder': 'Search for a ski area…',
                    'data-width': '100%',
                    'data-theme': 'bootstrap-5',
                },
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['date'].input_formats = ['%Y-%m-%d']
        self.fields['ski_area'].required = False
        self.fields['season_pass'].required = False
        self.fields['season_pass'].empty_label = 'Not covered by a pass'
        if user is not None:
            self.fields['activity_type'].queryset = SummerActivityType.for_user(user)
            # Limit pass choices to the user's own season passes.
            from cost.models import SeasonPass
            self.fields['season_pass'].queryset = (
                SeasonPass.objects.filter(user=user).order_by('-valid_until')
            )
        # Prefill the km/minute helper fields when editing an existing instance.
        if self.instance and self.instance.pk:
            if self.instance.distance is not None:
                self.fields['distance_km'].initial = round(self.instance.distance / 1000, 2)
            if self.instance.duration is not None:
                self.fields['duration_minutes'].initial = int(self.instance.duration.total_seconds() // 60)

    def save(self, commit=True):
        instance = super().save(commit=False)
        distance_km = self.cleaned_data.get('distance_km')
        instance.distance = float(distance_km) * 1000 if distance_km is not None else None
        duration_minutes = self.cleaned_data.get('duration_minutes')
        instance.duration = timedelta(minutes=duration_minutes) if duration_minutes else None
        if self.user is not None and not instance.user_id:
            instance.user = self.user
        if commit:
            instance.save()
        return instance