from django.apps import AppConfig

class ParlourConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parlour'

    def ready(self):
        import os
        # Prevent double-start when Django's reloader spawns a second process
        if os.environ.get('RUN_MAIN') != 'true':
            return
        from . import scheduler
        scheduler.start()
        from . import signals  # ← register signals