from django.core.exceptions import PermissionDenied, ValidationError

from core.locking import is_locked
from core.models import ClassSubject
from core.permissions import can
from report_cards.calculations import class_results
from report_cards.cards import get_or_create_draft
from report_cards.comments import comments_for


def approval_problems(student, term):
    """Every reason this student's card cannot be approved yet. Empty means ready."""
    problems = []

    school_class = student.school_class
    if school_class is None:
        return ['The student is not in a class.']

    class_subjects = list(
        ClassSubject.objects.filter(school_class=school_class).select_related('subject')
    )
    if not class_subjects:
        return ['The class has no subjects set up.']

    results = class_results(school_class, term, [student])
    row = results[0]

    for entry in row['subjects']:
        subject = entry['subject']
        if not entry['complete']:
            detail = ', '.join(entry['missing']) or 'incomplete'
            problems.append(f'{subject.name}: result incomplete ({detail}).')

    for class_subject in class_subjects:
        if not is_locked(class_subject, term):
            problems.append(f'{class_subject.subject.name}: results are not locked yet.')

    return problems


def approve_card(student, term, user):
    """Approve a student's report card if every check passes.

    Raises PermissionDenied if the user lacks the capability, and ValidationError
    listing every problem otherwise. On success the card is frozen with a snapshot.
    """
    if not can(user, 'approve_report_cards'):
        raise PermissionDenied

    card = get_or_create_draft(student, term)
    if card.is_frozen:
        raise ValidationError('This report card is already approved.')

    problems = approval_problems(student, term)
    if problems:
        raise ValidationError(problems)

    snapshot = build_snapshot(student, term)
    card.freeze(snapshot, user=user)
    return card


def build_snapshot(student, term):
    """The figures a printed card shows, stored as plain data.

    Decimals become strings so the JSON stored in the database stays exact.
    """
    school_class = student.school_class
    row = class_results(school_class, term, [student])[0]

    subjects = []
    for entry in row['subjects']:
        subjects.append({
            'subject': entry['subject'].name,
            'total': str(entry['total']),
            'grade': entry['grade'],
            'remark': entry['remark'],
            'position': entry['position'],
        })

    attendance = row['attendance'] or {}
    comments = comments_for(student, term)

    return {
        'student_id': student.student_id,
        'student_name': f'{student.last_name} {student.first_name}',
        'class': school_class.name,
        'term': str(term),
        'subjects': subjects,
        'average': str(row['average']) if row['average'] is not None else None,
        'position': row['position'],
        'attendance': {
            'marked': attendance.get('marked', 0),
            'present': attendance.get('present', 0),
            'absent': attendance.get('absent', 0),
            'late': attendance.get('late', 0),
            'excused': attendance.get('excused', 0),
            'percentage': (
                str(attendance['percentage']) if attendance.get('percentage') is not None else None
            ),
        },
        'class_teacher_comment': comments['class_teacher'].text if 'class_teacher' in comments else '',
        'head_teacher_remark': comments['head_teacher'].text if 'head_teacher' in comments else '',
    }