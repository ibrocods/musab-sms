from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models import SchoolProfile
from core.permissions import can

from .models import ReportComment


def _check_length(text):
    limit = SchoolProfile.get().comment_max_length
    if len(text) > limit:
        raise ValidationError(f'Comments can be at most {limit} characters. This one has {len(text)}.')


def _is_class_teacher(user, student, term):
    """True if the user is the class teacher for this student's class."""
    school_class = student.school_class
    return bool(school_class and school_class.class_teacher_id == user.pk)


def save_class_comment(student, term, text, user):
    """The class teacher writes the progress comment for their own class."""
    if not can(user, 'write_class_comment'):
        raise PermissionDenied
    if not _is_class_teacher(user, student, term):
        raise PermissionDenied

    text = (text or '').strip()
    _check_length(text)
    with transaction.atomic():
        comment, _ = ReportComment.objects.update_or_create(
            student=student, term=term, kind='class_teacher',
            defaults={'text': text, 'written_by': user},
        )
    return comment


def save_head_remark(student, term, text, user):
    """The head teacher writes the closing remark for any student."""
    if not can(user, 'write_head_remark'):
        raise PermissionDenied

    text = (text or '').strip()
    _check_length(text)
    with transaction.atomic():
        comment, _ = ReportComment.objects.update_or_create(
            student=student, term=term, kind='head_teacher',
            defaults={'text': text, 'written_by': user},
        )
    return comment


def comments_for(student, term):
    """Both comments for one student in one term, as a dict keyed by kind."""
    found = ReportComment.objects.filter(student=student, term=term)
    return {c.kind: c for c in found}