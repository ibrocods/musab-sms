from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .locking import is_locked, set_lock
from .models import Assessment, ClassSubject, Score, Term
from .permissions import can, require_capability
from .scope import visible_students
from .scoring import can_enter_scores, parse_score, save_score
from .terms import current_term


@login_required
@require_capability('enter_grades')
def score_index(request):
    term = current_term()
    entries = []
    if term:
        for class_subject in ClassSubject.objects.select_related('school_class', 'subject'):
            if can_enter_scores(request.user, class_subject):
                entries.append({
                    'class_subject': class_subject,
                    'assessments': Assessment.objects.filter(subject=class_subject.subject, term=term),
                    'locked': is_locked(class_subject, term),
                })
    return render(request, 'scores/index.html', {'term': term, 'entries': entries})


@login_required
@require_capability('enter_grades')
@require_http_methods(['GET', 'POST'])
def score_entry(request, class_subject_pk, assessment_pk):
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('school_class', 'subject'), pk=class_subject_pk,
    )
    assessment = get_object_or_404(Assessment.objects.select_related('subject', 'term'), pk=assessment_pk)

    if assessment.subject_id != class_subject.subject_id:
        raise Http404('This assessment belongs to a different subject.')
    if not can_enter_scores(request.user, class_subject):
        raise PermissionDenied

    locked = is_locked(class_subject, assessment.term)
    if request.method == 'POST' and locked:
        raise PermissionDenied

    students = list(
        visible_students(request.user)
        .filter(school_class=class_subject.school_class, is_archived=False)
        .order_by('last_name', 'first_name')
    )
    existing = {s.student_id: s.score for s in Score.objects.filter(assessment=assessment, student__in=students)}

    errors = {}
    submitted = {}
    if request.method == 'POST':
        values = {}
        for student in students:
            raw = request.POST.get(f'score_{student.pk}', '')
            submitted[student.pk] = raw
            try:
                values[student.pk] = parse_score(raw, assessment.max_mark)
            except ValidationError as error:
                errors[student.pk] = error.messages[0]

        # All or nothing: if any mark is invalid, nothing is saved
        if not errors:
            with transaction.atomic():
                for student in students:
                    save_score(student, assessment, values[student.pk], request.user)
            messages.success(request, 'Scores saved.')
            return redirect(request.path)

    rows = []
    for student in students:
        if request.method == 'POST':
            value = submitted[student.pk]
        else:
            stored = existing.get(student.pk)
            value = '' if stored is None else stored
        rows.append({'student': student, 'value': value, 'error': errors.get(student.pk)})

    return render(request, 'scores/entry.html', {
        'class_subject': class_subject,
        'assessment': assessment,
        'rows': rows,
        'locked': locked,
        'can_lock': can(request.user, 'lock_results'),
    })


@login_required
@require_capability('lock_results')
@require_POST
def result_lock(request, class_subject_pk, term_pk):
    class_subject = get_object_or_404(ClassSubject, pk=class_subject_pk)
    term = get_object_or_404(Term, pk=term_pk)
    locking = request.POST.get('action') == 'lock'
    try:
        set_lock(class_subject, term, locking=locking, user=request.user,
                 reason=request.POST.get('reason', ''))
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    else:
        messages.success(request, 'Results locked.' if locking else 'Results unlocked.')
    return redirect('score_index')