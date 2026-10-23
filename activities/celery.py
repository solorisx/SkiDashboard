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
    import logging

    # Apply Django logging config
    dictConfig(settings.LOGGING)

    # Configure Celery's internal loggers to use JSON format
    celery_loggers = ["celery.worker", "celery.task", "celery.redirected"]
    for logger_name in celery_loggers:
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        handler = logging.StreamHandler()

        class JSONFormatter(logging.Formatter):
            def format(self, record):
                import json

                log_data = {
                    "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage().replace("\n", "\\n"),
                }
                return json.dumps(log_data)

        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(settings.LOG_LEVEL)


app.autodiscover_tasks()
