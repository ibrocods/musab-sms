import csv

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render

from .models import Term
from .permissions import require_capability
from .reports import class_average, student_rows
from .scope import visible_classes, visible_students
from .terms import current_term


def _int_or_none(raw):
    return int(raw) if raw and raw.isdigit() else None


def _selection(request):
    """The term and class chosen in the query string, limited to what this user can see."""
    term_pk = _int_or_none(request.GET.get('term'))
    class_pk = _int_or_none(request.GET.get('class'))
    term = Term.objects.filter(pk=term_pk).first() if term_pk else current_term()
    school_class = visible_classes(request.user).filter(pk=class_pk).first() if class_pk else None
    return term, school_class


def _class_rows(user, term, school_class):
    students = (
        visible_students(user)
        .filter(school_class=school_class, is_archived=False)
        .order_by('last_name', 'first_name')
    )
    return student_rows(students, term)


@login_required
@require_capability('view_attendance')
def attendance_report(request):
    term, school_class = _selection(request)
    context = {
        'terms': Term.objects.all(),
        'classes': visible_classes(request.user).filter(is_active=True),
        'term': term,
        'school_class': school_class,
        'rows': [],
        'average': None,
    }
    if term and school_class:
        rows = _class_rows(request.user, term, school_class)
        context['rows'] = rows
        context['average'] = class_average(rows)
    return render(request, 'reports/attendance.html', context)


@login_required
@require_capability('view_attendance')
def attendance_report_csv(request):
    term, school_class = _selection(request)
    if not (term and school_class):
        raise Http404('Choose a term and a class first.')

    rows = _class_rows(request.user, term, school_class)
    session_part = term.session.replace('/', '-')
    filename = f'attendance_{school_class.name}_{session_part}_term{term.term_number}.csv'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Student ID', 'Last name', 'First name', 'Days marked',
        'Present', 'Absent', 'Late', 'Excused', 'Attendance %',
    ])
    for row in rows:
        writer.writerow([
            row['student'].student_id,
            row['student'].last_name,
            row['student'].first_name,
            row['marked'],
            row['present'],
            row['absent'],
            row['late'],
            row['excused'],
            '' if row['percentage'] is None else row['percentage'],
        ])
    return response