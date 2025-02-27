from django import forms
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount

User = get_user_model()

class StravaSyncForm(forms.Form):
    strava_activity_id = forms.CharField(label="Strava Activity ID", widget=forms.TextInput(attrs={"class": "form-control"}))
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(socialaccount__provider='strava'),
        label="User",
        widget=forms.Select(attrs={"class": "form-control"})
    )