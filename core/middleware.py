from django.shortcuts import redirect
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)


class ProfileConfirmationMiddleware:
    """
    Middleware to ensure users confirm their profile settings after signup.
    Redirects to profile page if profile is not confirmed, except for specific URLs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is authenticated
        if request.user.is_authenticated:
            # Skip check for certain URLs
            exempt_paths = [
                reverse("profile_management"),
                reverse("account_logout"),
                reverse("account_delete"),
                "/admin/",  # Django admin
                "/static/",  # Static files
                "/media/",  # Media files
            ]

            # Check if current path should be skipped
            current_path = request.path
            is_exempt = any(current_path.startswith(path) for path in exempt_paths)

            if not is_exempt:
                try:
                    profile = request.user.userprofile
                    if not profile.profile_confirmed:
                        logger.info(
                            f"User {request.user.username} has not confirmed profile, redirecting to profile page"
                        )
                        return redirect("profile_management")
                except Exception as e:
                    # If UserProfile doesn't exist or any other error, let it pass
                    # The profile will be created when they visit the profile page
                    logger.debug(f"ProfileConfirmationMiddleware exception: {e}")
                    pass

        response = self.get_response(request)
        return response
