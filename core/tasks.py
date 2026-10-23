from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from datetime import timedelta
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

        msg = EmailMultiAlternatives(subject=subject, body=body, from_email=from_email, to=to_emails)

        if html_body:
            msg.attach_alternative(html_body, "text/html")

        msg.send()

        logger.info(f"Email sent successfully to {to_emails}")
        return True

    except Exception as exc:
        logger.error(f"Failed to send email to {to_emails}: {exc}", exc_info=True)
        # Retry the task
        raise self.retry(exc=exc)


@shared_task
def send_premium_expiry_reminders():
    """Daily task: send 30-day and 7-day expiry warning emails to expiring premium users."""
    from django.utils import timezone
    from django.conf import settings
    from core.models import UserProfile

    now = timezone.now()
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

    # 30-day reminders
    for profile in UserProfile.objects.filter(
        is_premium=True,
        premium_expiry_30d_notified=False,
        premium_expires_at__range=(now, now + timedelta(days=31)),
    ).select_related("user"):
        subject = "Your SlopeLog Premium expires in 30 days"
        body = (
            f"Hi {profile.user.get_full_name() or profile.user.username},\n\n"
            f"Your SlopeLog Premium membership expires on "
            f"{profile.premium_expires_at.strftime('%B %d, %Y')}.\n\n"
            "To keep full access to all seasons and unlimited sync history, "
            "consider supporting the project again at https://buymeacoffee.com/slopelog\n\n"
            "Thanks for being a supporter!\nThe SlopeLog Team"
        )
        send_email_async.delay(subject, body, from_email, [profile.user.email])
        profile.premium_expiry_30d_notified = True
        profile.save(update_fields=["premium_expiry_30d_notified"])
        logger.info(f"Sent 30-day expiry reminder to {profile.user.email}")

    # 7-day reminders
    for profile in UserProfile.objects.filter(
        is_premium=True,
        premium_expiry_7d_notified=False,
        premium_expires_at__range=(now, now + timedelta(days=8)),
    ).select_related("user"):
        subject = "Your SlopeLog Premium expires in 7 days"
        body = (
            f"Hi {profile.user.get_full_name() or profile.user.username},\n\n"
            f"Your SlopeLog Premium expires on "
            f"{profile.premium_expires_at.strftime('%B %d, %Y')} — that's in about 7 days.\n\n"
            "Support the project to keep full access: https://buymeacoffee.com/slopelog\n\n"
            "Thanks!\nThe SlopeLog Team"
        )
        send_email_async.delay(subject, body, from_email, [profile.user.email])
        profile.premium_expiry_7d_notified = True
        profile.save(update_fields=["premium_expiry_7d_notified"])
        logger.info(f"Sent 7-day expiry reminder to {profile.user.email}")
