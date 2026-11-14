from decimal import ROUND_HALF_UP, Decimal

from core.grading import grade_for
from core.models import Assessment, ClassSubject, Score
from core.reports import student_rows

TWO_PLACES = Decimal('0.01')
ZERO = Decimal('0')


def _round(value):
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _rank(value, all_values):
    """Competition ranking: 1 is highest, tied values share a rank, and the next rank skips.

    Values are rounded before comparing, so results that display as equal also tie.
    Returns None when there is no value.
    """
    if value is None:
        return None
    return 1 + sum(1 for other in all_values if other is not None and other > value)


def subject_result(student, class_subject, term):
    """One student's result in one subject, out of 100.

    Each assessment adds (mark / maximum) x weight. A missing mark makes the subject
    incomplete, so it has no total. A missing mark is never counted as zero.
    """
    assessments = list(Assessment.objects.filter(subject=class_subject.subject, term=term))
    if not assessments:
        return {'total': None, 'grade': None, 'remark': '', 'complete': False,
                'missing': ['no assessments set up']}

    for assessment in assessments:
        if assessment.max_mark <= 0:
            raise ValueError(f'{assessment} has a maximum mark of zero. Fix it in the admin.')

    weights = sum((a.weight for a in assessments), ZERO)
    if weights != Decimal('100'):
        return {'total': None, 'grade': None, 'remark': '', 'complete': False,
                'missing': ['weights do not total 100']}

    marks = {
        score.assessment_id: score.score
        for score in Score.objects.filter(student=student, assessment__in=assessments)
    }

    total = ZERO
    missing = []
    for assessment in assessments:
        mark = marks.get(assessment.pk)
        if mark is None:
            missing.append(assessment.name)
        else:
            total += (mark / assessment.max_mark) * assessment.weight

    if missing:
        return {'total': None, 'grade': None, 'remark': '', 'complete': False, 'missing': missing}

    total = _round(total)
    band = grade_for(total)
    return {'total': total, 'grade': band.grade, 'remark': band.remark,
            'complete': True, 'missing': []}


def class_results(school_class, term, students):
    """Results for every student in a class: subjects, positions, averages and attendance."""
    students = list(students)
    class_subjects = list(
        ClassSubject.objects.filter(school_class=school_class).select_related('subject')
    )

    rows = []
    for student in students:
        subjects = []
        for class_subject in class_subjects:
            result = subject_result(student, class_subject, term)
            subjects.append({'subject': class_subject.subject, **result})
        rows.append({'student': student, 'subjects': subjects})

    # Subject positions: compare each student's total in the same subject
    for index in range(len(class_subjects)):
        totals = [row['subjects'][index]['total'] for row in rows]
        for row in rows:
            entry = row['subjects'][index]
            entry['position'] = _rank(entry['total'], totals)

    # Overall average: only for students whose every subject is complete
    for row in rows:
        complete = [s['total'] for s in row['subjects'] if s['complete']]
        all_done = bool(row['subjects']) and len(complete) == len(row['subjects'])
        row['complete'] = all_done
        row['average'] = _round(sum(complete, ZERO) / len(complete)) if all_done else None

    # Overall position: compare averages across the class
    averages = [row['average'] for row in rows]
    for row in rows:
        row['position'] = _rank(row['average'], averages)

    # Attendance for the term, using the same figures as the attendance report
    attendance = {r['student'].pk: r for r in student_rows(students, term)}
    for row in rows:
        row['attendance'] = attendance.get(row['student'].pk)

    return rows


def subject_class_average(results, subject):
    """Average of the complete totals in one subject across the class."""
    totals = [
        entry['total']
        for row in results
        for entry in row['subjects']
        if entry['subject'] == subject and entry['complete']
    ]
    if not totals:
        return None
    return _round(sum(totals, ZERO) / len(totals))