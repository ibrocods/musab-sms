from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import AttendanceRecord
from .permissions import can
from .scope import visible_classes


def can_mark(user, school_class):
    """Mark attendance only if the role allows it and the class is in the user's scope."""
    if not can(user, 'mark_attendance'):
        return False
    return visible_classes(user).filter(pk=school_class.pk).exists()


def save_register(school_class, term, day, entries, user):
    """Save one day's register for one class.

    entries maps each student to a status code ('P', 'A', 'L', 'E'), or to None
    to clear that student's mark. Everything is checked before anything is written.
    """
    if not can_mark(user, school_class):
        raise PermissionDenied

    if not (term.start_date <= day <= term.end_date):
        raise ValidationError(
            f'{day:%d %b %Y} is outside {term}. Choose a date within the term.'
        )

    for student in entries:
        if student.school_class_id != school_class.pk:
            raise ValidationError(f'{student} is not in {school_class}.')

    with transaction.atomic():
        for student, code in entries.items():
            if code is None:
                AttendanceRecord.objects.filter(student=student, date=day).delete()
            else:
                AttendanceRecord.objects.update_or_create(
                    student=student,
                    date=day,
                    defaults={
                        'school_class': school_class,
                        'term': term,
                        'status': code,
                        'marked_by': user,
                    },
                )