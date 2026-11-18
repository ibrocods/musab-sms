from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.models import ClassSubject, SchoolClass, Student, Subject
from core.permissions import require_capability

from .setup_forms import ClassForm, ClassSubjectForm, SubjectForm
from .setup_rules import remove_class_subject


def _error_text(error):
    return ' '.join(getattr(error, 'messages', ['You do not have permission.']))


@login_required
@require_capability('manage_school_setup')
@require_GET
def setup_home(request):
    return render(request, 'school_admin/setup_home.html', {
        'subject_count': Subject.objects.filter(is_active=True).count(),
        'class_count': SchoolClass.objects.filter(is_active=True).count(),
    })


# Subjects

@login_required
@require_capability('manage_school_setup')
@require_GET
def subject_list(request):
    subjects = Subject.objects.annotate(
        class_count=Count('class_subjects', distinct=True),
    ).order_by('name')
    return render(request, 'school_admin/subjects.html', {'subjects': subjects})


@login_required
@require_capability('manage_school_setup')
@require_http_methods(['GET', 'POST'])
def subject_create(request):
    form = SubjectForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Subject added.')
        return redirect('school_admin:subject_list')
    return render(request, 'school_admin/form_page.html', {
        'form': form,
        'title': 'Add a subject',
        'subtitle': 'Once added, a subject can be given to any class from the class page.',
        'submit_label': 'Add subject',
        'cancel_url': reverse('school_admin:subject_list'),
    })


@login_required
@require_capability('manage_school_setup')
@require_http_methods(['GET', 'POST'])
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    form = SubjectForm(request.POST or None, instance=subject)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Subject saved.')
        return redirect('school_admin:subject_list')
    return render(request, 'school_admin/form_page.html', {
        'form': form,
        'title': f'Edit {subject.name}',
        'submit_label': 'Save subject',
        'cancel_url': reverse('school_admin:subject_list'),
    })


@login_required
@require_capability('manage_school_setup')
@require_POST
def subject_toggle(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    subject.is_active = not subject.is_active
    subject.save()
    messages.success(request, f"{subject.name} is now {'active' if subject.is_active else 'inactive'}.")
    return redirect('school_admin:subject_list')


# Classes

@login_required
@require_capability('manage_school_setup')
@require_GET
def class_list(request):
    classes = (
        SchoolClass.objects.select_related('class_teacher')
        .annotate(
            subject_count=Count('class_subjects', distinct=True),
            student_count=Count('students', filter=Q(students__is_archived=False), distinct=True),
        )
        .order_by('name')
    )
    return render(request, 'school_admin/classes.html', {'classes': classes})


@login_required
@require_capability('manage_school_setup')
@require_http_methods(['GET', 'POST'])
def class_create(request):
    form = ClassForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        school_class = form.save()
        messages.success(request, f'{school_class.name} added.')
        return redirect('school_admin:class_detail', pk=school_class.pk)
    return render(request, 'school_admin/form_page.html', {
        'form': form,
        'title': 'Add a class',
        'subtitle': 'Students are placed in a class when they are added. Subjects are added on the class page.',
        'submit_label': 'Add class',
        'cancel_url': reverse('school_admin:class_list'),
    })


@login_required
@require_capability('manage_school_setup')
@require_http_methods(['GET', 'POST'])
def class_edit(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    form = ClassForm(request.POST or None, instance=school_class)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{school_class.name} saved.')
        return redirect('school_admin:class_detail', pk=school_class.pk)
    return render(request, 'school_admin/form_page.html', {
        'form': form,
        'title': f'Edit {school_class.name}',
        'submit_label': 'Save class',
        'cancel_url': reverse('school_admin:class_detail', args=[school_class.pk]),
    })


@login_required
@require_capability('manage_school_setup')
@require_POST
def class_toggle(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    school_class.is_active = not school_class.is_active
    school_class.save()
    messages.success(
        request,
        f"{school_class.name} is now {'active' if school_class.is_active else 'inactive'}. "
        'Its students and history are kept.',
    )
    return redirect('school_admin:class_list')


@login_required
@require_capability('manage_school_setup')
@require_GET
def class_detail(request, pk):
    school_class = get_object_or_404(SchoolClass.objects.select_related('class_teacher'), pk=pk)
    links = (
        ClassSubject.objects.filter(school_class=school_class)
        .select_related('subject', 'teacher')
        .order_by('subject__name')
    )
    student_count = Student.objects.filter(school_class=school_class, is_archived=False).count()
    return render(request, 'school_admin/class_detail.html', {
        'school_class': school_class,
        'links': links,
        'student_count': student_count,
    })


@login_required
@require_capability('manage_school_setup')
@require_http_methods(['GET', 'POST'])
def class_subject_add(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    form = ClassSubjectForm(request.POST or None, school_class=school_class)
    if request.method == 'POST' and form.is_valid():
        link = form.save(commit=False)
        link.school_class = school_class
        link.save()
        messages.success(request, f'{link.subject.name} added to {school_class.name}.')
        return redirect('school_admin:class_detail', pk=school_class.pk)
    return render(request, 'school_admin/form_page.html', {
        'form': form,
        'title': f'Add a subject to {school_class.name}',
        'subtitle': 'Choose the subject and, if you know it, the teacher. The teacher can be assigned later.',
        'submit_label': 'Add subject',
        'cancel_url': reverse('school_admin:class_detail', args=[school_class.pk]),
    })


@login_required
@require_capability('manage_school_setup')
@require_POST
def class_subject_remove(request, pk):
    link = get_object_or_404(ClassSubject.objects.select_related('school_class', 'subject'), pk=pk)
    class_pk = link.school_class_id
    try:
        remove_class_subject(actor=request.user, link=link)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, 'Subject removed from the class.')
    return redirect('school_admin:class_detail', pk=class_pk)