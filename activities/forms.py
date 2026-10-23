from django import forms
from django.contrib.auth import get_user_model

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