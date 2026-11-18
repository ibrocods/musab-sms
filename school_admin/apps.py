from django.apps import AppConfig


class SchoolAdminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'school_admin'

    def ready(self):
        from core.models import ClassSubject, Subject
        from core.signals import track
        track(ClassSubject)
        track(Subject)