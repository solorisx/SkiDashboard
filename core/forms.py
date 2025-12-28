from django import forms
from .models import UserProfile
from osm.models import LiftFilterConfig
from allauth.socialaccount.models import SocialAccount

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
    # User account fields (not part of UserProfile model)
    username = forms.CharField(
        max_length=150,
        required=True,
        help_text="Your display name",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        required=False,
        disabled=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
    )

    excluded_lift_types = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select lift types to exclude from your statistics"
    )

    class Meta:
        model = UserProfile
        fields = [
            # 'language', 'timezone', 'metric_units', 'dark_mode',
            'excluded_lift_types', 'season_start_month', 'season_start_day',
            'opt_in_newsletter', 'opt_in_summary_email', 'opt_in_strava_write'
        ]
        widgets = {
            #'language': forms.Select(attrs={'class': 'form-select'}),
            #'timezone': forms.Select(attrs={'class': 'form-select'}),
            #'metric_units': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            #'dark_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'season_start_month': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'season_start_day': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
            'opt_in_newsletter': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'opt_in_summary_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'opt_in_strava_write': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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

            # Set initial values for username and email from User model
            if self.instance.user:
                self.fields['username'].initial = self.instance.user.username
                self.fields['email'].initial = self.instance.user.email

    def clean_username(self):
        """Validate that username is unique (excluding current user)."""
        from django.contrib.auth.models import User
        username = self.cleaned_data.get('username')

        if username:
            # Check if username already exists for a different user
            user_id = self.instance.user.id if self.instance and self.instance.pk else None
            if User.objects.filter(username=username).exclude(id=user_id).exists():
                raise forms.ValidationError("This username is already taken. Please choose another one.")

        return username

    def clean_opt_in_strava_write(self):
        """Validate that user has Strava connected before enabling write access."""
        opt_in_strava_write = self.cleaned_data.get('opt_in_strava_write')

        # Only validate if trying to enable (True)
        if opt_in_strava_write:
            # Check if user has Strava account connected
            user = self.instance.user if self.instance and self.instance.pk else None
            if user:
                has_strava = SocialAccount.objects.filter(
                    user=user,
                    provider="strava"
                ).exists()

                if not has_strava:
                    raise forms.ValidationError(
                        "You must connect your Strava account before enabling write access. "
                        "Please connect Strava first."
                    )

        return opt_in_strava_write

    def save(self, commit=True):
        logger.debug("Saving UserProfileForm with cleaned_data: %s", self.cleaned_data)
        instance = super().save(commit=False)

        # Update username on User model if changed
        new_username = self.cleaned_data.get('username')
        if new_username and instance.user.username != new_username:
            instance.user.username = new_username
            instance.user.save()
            logger.info(f"Updated username to: {new_username}")

        # Convert excluded_lift_types to list for JSONField
        instance.excluded_lift_types = self.cleaned_data.get('excluded_lift_types', [])
        logger.debug("commit=%s, excluded_lift_types=%s", commit, instance.excluded_lift_types)

        if commit:
            instance.save()
        return instance