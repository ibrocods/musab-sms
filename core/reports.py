from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q

from .models import AttendanceRecord


def _percentage(attended, expected):
    if expected <= 0:
        return None
    value = Decimal(attended) * 100 / Decimal(expected)
    return value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)


def student_rows(students, term):
    """Attendance totals for each student in one term."""
    students = list(students)

    # .order_by() clears the model's default ordering, which would otherwise
    # break the grouping in this aggregate query
    totals = (
        AttendanceRecord.objects.filter(term=term, student__in=students)
        .order_by()
        .values('student')
        .annotate(
            marked=Count('id'),
            present=Count('id', filter=Q(status='P')),
            absent=Count('id', filter=Q(status='A')),
            late=Count('id', filter=Q(status='L')),
            excused=Count('id', filter=Q(status='E')),
        )
    )
    by_student = {row['student']: row for row in totals}

    rows = []
    for student in students:
        t = by_student.get(student.pk, {})
        marked = t.get('marked', 0)
        present = t.get('present', 0)
        late = t.get('late', 0)
        excused = t.get('excused', 0)
        rows.append({
            'student': student,
            'marked': marked,
            'present': present,
            'absent': t.get('absent', 0),
            'late': late,
            'excused': excused,
            'percentage': _percentage(present + late, marked - excused),
        })
    return rows


def class_average(rows):
    """Average of the students' percentages, ignoring students with no countable days."""
    values = [row['percentage'] for row in rows if row['percentage'] is not None]
    if not values:
        return None
    return (sum(values) / len(values)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)