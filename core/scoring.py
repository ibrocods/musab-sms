from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from .grading import grade_for
from .models import Score


def can_enter_scores(user, class_subject):
    """Who may enter marks for a class and subject.

    Allowed: superusers, the teacher assigned to the subject, and the class teacher.
    The class teacher can enter any subject for their own class. If a school wants
    stricter rules, change this one function.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if class_subject.teacher_id == user.pk:
        return True
    return class_subject.school_class.class_teacher_id == user.pk


def parse_score(raw, max_mark):
    """Turn a form value into a Decimal, or None if left blank."""
    text = (raw or '').strip()
    if text == '':
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValidationError('Enter a number.')
    if value < 0 or value > max_mark:
        raise ValidationError(f'Enter a mark between 0 and {max_mark}.')
    return value.quantize(Decimal('0.01'))


def save_score(student, assessment, value, user):
    """Save one mark. A blank value removes the existing mark."""
    if value is None:
        Score.objects.filter(student=student, assessment=assessment).delete()
        return
    Score.objects.update_or_create(
        student=student,
        assessment=assessment,
        defaults={'score': value, 'entered_by': user},
    )


def percentage(score):
    max_mark = score.assessment.max_mark
    if not max_mark:
        raise ValueError('The assessment maximum must be greater than zero.')
    return (score.score / max_mark) * Decimal('100')


def grade_for_score(score):
    """The grade band for a saved mark, using the school's grade bands."""
    return grade_for(percentage(score))