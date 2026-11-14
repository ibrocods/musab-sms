from django.apps import AppConfig


class ReportCardsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'report_cards'

    def ready(self):
        from core.signals import track
        from .models import ReportComment
        track(ReportComment)