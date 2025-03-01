from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from django.contrib.auth.models import User
from .models import UserProfile

@receiver(user_signed_up)
def create_user_profile(request, user, **kwargs):
    """
    This signal is triggered when a new user signs up via allauth.
    It automatically creates a UserProfile instance.
    """
    UserProfile.objects.get_or_create(user=user)