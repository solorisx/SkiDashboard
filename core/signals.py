import logging
from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from .models import UserProfile

logger = logging.getLogger(__name__)

@receiver(user_signed_up)
def create_user_profile(request, user, **kwargs):
    """
    This signal is triggered when a new user signs up via allauth.
    It automatically creates a UserProfile instance.
    """
    UserProfile.objects.get_or_create(user=user)


@receiver(user_signed_up)
def notify_admin_new_user(request, user, **kwargs):
    """
    Send email notification to admin when a new user signs up via allauth
    """
    try:
        # Get user details
        user_id = user.id
        user_profile_id = UserProfile.objects.get(user=user).id
        date_joined = user.date_joined.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Get signup method (email vs social)
        signup_method = 'Email Registration'
        if hasattr(request, 'session') and 'socialaccount_sociallogin' in request.session:
            signup_method = 'Social Account (Strava)'
        
        # Email subject
        subject = f'New Ski Dashboard User: {user_id}'
        
        # Email content
        message = f"""
A new user has joined Ski Dashboard!
User ID: {user_id}
User Profile ID: {user_profile_id}
Date Joined: {date_joined}
Signup Method: {signup_method}

Number of Users now: {User.objects.count()}

🔗 Admin Links:
   • View User: /admin/auth/user/{user.id}/change/
   • User Profile: /admin/core/userprofile/{user_profile_id}/change/
    """.strip()
        
        # Send email to admin
        admin_email = getattr(settings, 'DEFAULT_FROM_EMAIL')
        if not admin_email:
            logger.warning("DEFAULT_FROM_EMAIL is not set in settings. Cannot send admin notification.")
            return        
        send_mail(
            subject=subject,
            message=message,
            from_email=admin_email,
            recipient_list=[admin_email],
            fail_silently=False,
        )
        logger.info(f"Admin notification sent for new user: {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to send admin notification for new user {user_id}: {str(e)}")