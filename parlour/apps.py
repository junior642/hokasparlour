from django.apps import AppConfig
import os

class ParlourConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parlour'

    def ready(self):
        # Always register signals
        from . import signals

        # Only start scheduler in dev (Django reloader process)
        if os.environ.get('RUN_MAIN') == 'true':
            from . import scheduler
            scheduler.start()
