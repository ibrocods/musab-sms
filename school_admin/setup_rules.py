from django.core.exceptions import PermissionDenied, ValidationError

from core.models import ResultLock, Score
from core.permissions import can


def remove_class_subject(*, actor, link):
    """Take a subject off a class, unless marks or locked results exist for it."""
    if not can(actor, 'manage_school_setup'):
        raise PermissionDenied
    if ResultLock.objects.filter(class_subject=link).exists():
        raise ValidationError('Results have been locked for this subject, so it cannot be removed.')
    if Score.objects.filter(
        student__school_class=link.school_class, assessment__subject=link.subject,
    ).exists():
        raise ValidationError('Marks have been entered for this subject, so it cannot be removed.')
    link.delete()