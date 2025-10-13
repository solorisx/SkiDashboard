"""Custom allauth account adapter with async email support."""
import logging
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.sites.shortcuts import get_current_site
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

        ctx = {
            "request": request,
            "email": email,
            "current_site": get_current_site(request),
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
        return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@skidashboard.app')
