from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .attendance import can_mark, save_register
from .models import AttendanceRecord
from .permissions import require_capability
from .scope import visible_classes, visible_students
from .terms import current_term

VALID_CODES = {code for code, _ in AttendanceRecord.STATUS_CHOICES}


def _parse_day(raw):
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return timezone.localdate()


def _students(user, school_class):
    return (
        visible_students(user)
        .filter(school_class=school_class, is_archived=False)
        .order_by('last_name', 'first_name')
    )


@login_required
@require_capability('view_attendance')
def attendance_index(request):
    classes = visible_classes(request.user).filter(is_active=True)
    return render(request, 'attendance/index.html', {
        'classes': classes,
        'term': current_term(),
        'today': timezone.localdate(),
    })


@login_required
@require_capability('view_attendance')
@require_http_methods(['GET', 'POST'])
def attendance_register(request, class_pk):
    # Classes outside the user's scope return 404, so they don't even learn the class exists
    school_class = get_object_or_404(visible_classes(request.user), pk=class_pk)
    term = current_term()
    day = _parse_day(request.GET.get('date'))
    allowed = can_mark(request.user, school_class)

    if request.method == 'POST':
        if not allowed:
            raise PermissionDenied

        if term is None:
            messages.error(request, 'No current term is set. Ask the administrator to mark one as current.')
            return redirect(request.get_full_path())

        entries = {}
        for student in _students(request.user, school_class):
            code = request.POST.get(f'status_{student.pk}', '')
            if code == '':
                entries[student] = None
            elif code in VALID_CODES:
                entries[student] = code
            else:
                return HttpResponseBadRequest('Unknown attendance code.')

        try:
            save_register(school_class, term, day, entries, request.user)
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        else:
            messages.success(request, 'Attendance saved.')
        return redirect(f'{request.path}?date={day.isoformat()}')

    existing = dict(
        AttendanceRecord.objects.filter(school_class=school_class, date=day)
        .values_list('student_id', 'status')
    )
    rows = [
        {'student': student, 'status': existing.get(student.pk, '')}
        for student in _students(request.user, school_class)
    ]
    return render(request, 'attendance/register.html', {
        'school_class': school_class,
        'term': term,
        'day': day,
        'rows': rows,
        'allowed': allowed,
        'status_choices': AttendanceRecord.STATUS_CHOICES,
    })