"""Custom allauth account adapter with async email support."""
import logging
from allauth.account.adapter import DefaultAccountAdapter
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


class AsyncEmailAccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter that sends emails asynchronously via Celery
    """

    def send_mail(self, template_prefix, email, context):
        """
        Override to send emails asynchronously via Celery.

        Args:
            template_prefix: Template path prefix (e.g., "account/email/password_reset_key")
            email: Recipient email address
            context: Context dict for rendering the email template
        """
        from core.tasks import send_email_async

        request = context.get('request')

        # Create a simple site object for email context
        class SimpleSite:
            def __init__(self):
                # Get domain from request or fall back to ALLOWED_HOSTS
                if request:
                    try:
                        self.domain = request.get_host()
                    except Exception:
                        self.domain = self._get_default_domain()
                else:
                    self.domain = self._get_default_domain()
                self.name = 'Ski Dashboard'

            def _get_default_domain(self):
                allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
                if allowed_hosts and allowed_hosts[0]:
                    return allowed_hosts[0]
                return 'localhost'

        current_site = SimpleSite()

        ctx = {
            "request": request,
            "email": email,
            "current_site": current_site,
        }
        ctx.update(context)

        # Render the email subject
        subject_template = f"{template_prefix}_subject.txt"
        subject = render_to_string(subject_template, ctx).strip()

        # Render the plain text body
        body_template = f"{template_prefix}_message.txt"
        body = render_to_string(body_template, ctx)

        # Try to render HTML version if it exists
        html_body = None
        try:
            html_template = f"{template_prefix}_message.html"
            html_body = render_to_string(html_template, ctx)
        except Exception as e:
            logger.debug(f"No HTML template found for {template_prefix}: {e}")

        # Get sender email
        from_email = self.get_from_email()

        # Send email asynchronously via Celery
        logger.info(f"Queueing email to {email} with subject: {subject}")

        try:
            send_email_async.delay(
                subject=subject,
                body=body,
                from_email=from_email,
                to_emails=[email],
                html_body=html_body
            )
            logger.info(f"Email queued successfully to {email}")
        except Exception as e:
            logger.error(f"Failed to queue email to {email}: {e}", exc_info=True)
            # Re-raise so allauth knows the email failed
            raise

    def get_from_email(self):
        """Get the sender email address."""
        return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@slopelog.com')

    def confirm_email(self, request, email_address):
        """
        Called after email is confirmed. Send a welcome email.
        """
        # Call the parent method first
        super().confirm_email(request, email_address)

        # Send welcome email
        user = email_address.user
        logger.info(f"Sending welcome email to {user.email}")

        # Use send_mail to send welcome email asynchronously
        context = {
            'user': user,
            'request': request,
        }
        self.send_mail('account/email/welcome', user.email, context)
