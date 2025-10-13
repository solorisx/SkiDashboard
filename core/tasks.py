from celery import shared_task
from django.core.mail import EmailMultiAlternatives
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_async(self, subject, body, from_email, to_emails, html_body=None):
    """
    Send email asynchronously via Celery to prevent blocking web workers.

    Args:
        subject: Email subject
        body: Plain text email body
        from_email: Sender email address
        to_emails: List of recipient email addresses
        html_body: Optional HTML version of the email body
    """
    try:
        logger.info(f"Sending email to {to_emails} with subject: {subject}")

        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=to_emails
        )

        if html_body:
            msg.attach_alternative(html_body, "text/html")

        msg.send()

        logger.info(f"Email sent successfully to {to_emails}")
        return True

    except Exception as exc:
        logger.error(f"Failed to send email to {to_emails}: {exc}", exc_info=True)
        # Retry the task
        raise self.retry(exc=exc)
