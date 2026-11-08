from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import StudentForm
from .permissions import can, require_capability
from .scope import visible_students


@login_required
@require_capability('view_students')
def student_list(request):
    students = visible_students(request.user).filter(is_archived=False).select_related('school_class')
    q = request.GET.get('q', '').strip()
    if q:
        students = students.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(student_id__icontains=q)
        )
    return render(request, 'students/list.html', {
        'students': students,
        'q': q,
        'can_manage': can(request.user, 'manage_students'),
    })


@login_required
@require_capability('manage_students')
def student_create(request):
    form = StudentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('student_list')
    return render(request, 'students/form.html', {'form': form, 'title': 'Add student'})


@login_required
@require_capability('manage_students')
@require_POST
def student_archive(request, pk):
    # Students are archived, never deleted, so records are kept
    student = get_object_or_404(visible_students(request.user), pk=pk)
    student.is_archived = True
    student.archived_at = timezone.now()
    student.save()
    return redirect('student_list')