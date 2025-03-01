from django.apps import AppConfig

class core(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals  # Import signals when the app is ready  
