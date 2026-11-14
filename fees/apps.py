from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fees'

    def ready(self):
        from core.signals import track
        from .models import FeeItem, Payment
        track(FeeItem)
        track(Payment)