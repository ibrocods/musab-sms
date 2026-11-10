from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import AttendanceRecord, AuditLog, NonSchoolDay, SchoolProfile
from .permissions import can
from .scope import visible_classes


def can_mark(user, school_class):
    """Mark attendance only if the role allows it and the class is in the user's scope."""
    if not can(user, 'mark_attendance'):
        return False
    return visible_classes(user).filter(pk=school_class.pk).exists()


def non_school_reason(day):
    """Return why a date isn't a school day, or None if it is one."""
    if day.weekday() not in SchoolProfile.get().school_day_numbers():
        return f'{day:%d %B %Y} is not a school day'
    holiday = NonSchoolDay.objects.filter(date=day).first()
    if holiday:
        return f'{day:%d %B %Y} is a non-school day ({holiday.description})'
    return None


def save_register(school_class, term, day, entries, user, notes=None):
    """Save one day's register for one class.

    entries maps each student to a status code ('P', 'A', 'L', 'E'), or None to clear.
    notes maps students to a text note. Excused absences must have a note.
    Everything is checked before anything is written, and the whole register is
    logged as one audit entry listing only the changes.
    """
    notes = notes or {}

    if not can_mark(user, school_class):
        raise PermissionDenied

    if not (term.start_date <= day <= term.end_date):
        raise ValidationError(f'{day:%d %b %Y} is outside {term}. Choose a date within the term.')

    reason = non_school_reason(day)
    if reason:
        raise ValidationError(f'{reason}. Choose another date.')

    for student, code in entries.items():
        if student.school_class_id != school_class.pk:
            raise ValidationError(f'{student} is not in {school_class}.')
        if code == 'E' and not notes.get(student, '').strip():
            raise ValidationError(f'{student} is marked Excused. Add a note explaining the absence.')

    previous = {
        student_pk: (status, note)
        for student_pk, status, note in
        AttendanceRecord.objects.filter(school_class=school_class, date=day)
        .values_list('student', 'status', 'note')
    }
    changes = {}

    with transaction.atomic():
        for student, code in entries.items():
            if code is None:
                AttendanceRecord.objects.filter(student=student, date=day).delete()
                after = (None, '')
            else:
                note = notes.get(student, '').strip()
                AttendanceRecord.objects.update_or_create(
                    student=student,
                    date=day,
                    defaults={
                        'school_class': school_class,
                        'term': term,
                        'status': code,
                        'note': note,
                        'marked_by': user,
                    },
                )
                after = (code, note)

            before = previous.get(student.pk, (None, ''))
            if before != after:
                changes[student.student_id] = {'before': list(before), 'after': list(after)}

        if changes:
            AuditLog.objects.create(
                user=user,
                username=user.get_username(),
                action='update',
                model_name='core.attendancerecord',
                object_id=f'{school_class.pk}:{day.isoformat()}',
                object_repr=f'{school_class.name} register {day:%Y-%m-%d}',
                changes=changes,
            )