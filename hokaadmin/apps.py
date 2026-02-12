from django.apps import AppConfig


class HokaadminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hokaadmin'
    
    def ready(self):
        import hokaadmin.signals