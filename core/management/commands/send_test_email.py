from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send a test email to verify email configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            type=str,
            default="contact@slopelog.com",
            help="Email address to send the test email to (default: contact@slopelog.com)",
        )

    def handle(self, *args, **options):
        recipient = options["to"]

        self.stdout.write(self.style.WARNING(f"Sending test email to {recipient}..."))
        self.stdout.write(f"Email backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f'SMTP host: {getattr(settings, "EMAIL_HOST", "N/A")}')
        self.stdout.write(f'SMTP port: {getattr(settings, "EMAIL_PORT", "N/A")}')
        self.stdout.write(f"From email: {settings.DEFAULT_FROM_EMAIL}")

        try:
            send_mail(
                subject="Test Email from SlopeLog",
                message=(
                    "This is a test email from your SlopeLog Django application.\n\n"
                    "If you received this email, your SMTP configuration is working correctly!\n\n"
                    "Email Configuration:\n"
                    f"- Backend: {settings.EMAIL_BACKEND}\n"
                    f'- Host: {getattr(settings, "EMAIL_HOST", "N/A")}\n'
                    f'- Port: {getattr(settings, "EMAIL_PORT", "N/A")}\n'
                    f'- TLS: {getattr(settings, "EMAIL_USE_TLS", "N/A")}\n'
                    f"- From: {settings.DEFAULT_FROM_EMAIL}\n\n"
                    "Best regards,\n"
                    "SlopeLog Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )

            self.stdout.write(self.style.SUCCESS(f"Test email sent successfully to {recipient}!"))

        except Exception as e:
            logger.error(f"Failed to send test email: {e}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"Failed to send test email: {e}"))
            raise
