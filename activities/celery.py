import os
from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("activities")

app.config_from_object("django.conf:settings", namespace="CELERY")

@setup_logging.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig
    from django.conf import settings
    dictConfig(settings.LOGGING)

app.autodiscover_tasks()