from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.models import SchoolClass, Term
from core.permissions import can, require_capability
from core.scope import visible_classes, visible_students
from core.terms import current_term

from .approval import approval_problems, approve_card
from .cards import get_or_create_draft
from .comments import comments_for, save_class_comment, save_head_remark
from .layouts import render_card
from .models import ReportCard


def _term(request):
    pk = request.GET.get('term') or request.POST.get('term')
    if pk and str(pk).isdigit():
        found = Term.objects.filter(pk=pk).first()
        if found:
            return found
    return current_term()


def _card_url(student, term):
    url = reverse('report_cards:card', args=[student.pk])
    return f'{url}?term={term.pk}' if term else url


@login_required
@require_capability('view_grades')
@require_GET
def report_card_index(request):
    term = _term(request)
    school_class = None
    rows = []
    class_pk = request.GET.get('class')
    if class_pk and class_pk.isdigit():
        school_class = visible_classes(request.user).filter(pk=class_pk).first()
    if term and school_class:
        students = visible_students(request.user).filter(school_class=school_class, is_archived=False)
        for student in students.order_by('last_name', 'first_name'):
            card = ReportCard.objects.filter(student=student, term=term).first()
            rows.append({'student': student, 'card': card})
    return render(request, 'report_cards/index.html', {
        'term': term,
        'terms': Term.objects.all(),
        'classes': visible_classes(request.user).filter(is_active=True),
        'school_class': school_class,
        'rows': rows,
    })


@login_required
@require_capability('view_grades')
@require_GET
def report_card_view(request, student_pk):
    student = get_object_or_404(visible_students(request.user), pk=student_pk)
    term = _term(request)
    if term is None:
        return render(request, 'report_cards/no_term.html')

    card = get_or_create_draft(student, term)
    frozen = card.is_frozen
    comments = comments_for(student, term)
    is_own_class = bool(student.school_class and student.school_class.class_teacher_id == request.user.pk)

    html = render_card(request, card)
    return render(request, 'report_cards/card_page.html', {
        'student': student,
        'term': term,
        'card': card,
        'card_html': html,
        'problems': [] if frozen else approval_problems(student, term),
        'can_approve': can(request.user, 'approve_report_cards') and not frozen,
        'can_comment': can(request.user, 'write_class_comment') and is_own_class and not frozen,
        'can_remark': can(request.user, 'write_head_remark') and not frozen,
        'class_comment': comments['class_teacher'].text if 'class_teacher' in comments else '',
        'head_remark': comments['head_teacher'].text if 'head_teacher' in comments else '',
        'comment_limit': _comment_limit(),
    })


def _comment_limit():
    from core.models import SchoolProfile
    return SchoolProfile.get().comment_max_length


@login_required
@require_capability('view_grades')
@require_POST
def report_card_comment(request, student_pk):
    student = get_object_or_404(visible_students(request.user), pk=student_pk)
    term = _term(request)
    if term is None:
        messages.error(request, 'No term is selected.')
        return redirect(reverse('report_cards:index'))

    kind = request.POST.get('kind')
    text = request.POST.get('text', '')
    try:
        if kind == 'class_teacher':
            save_class_comment(student, term, text, request.user)
        elif kind == 'head_teacher':
            save_head_remark(student, term, text, request.user)
        else:
            raise ValidationError('Unknown comment type.')
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    except PermissionDenied:
        messages.error(request, 'You do not have permission to write that comment.')
    else:
        messages.success(request, 'Comment saved.')
    return redirect(_card_url(student, term))


@login_required
@require_capability('approve_report_cards')
@require_POST
def report_card_approve(request, student_pk):
    student = get_object_or_404(visible_students(request.user), pk=student_pk)
    term = _term(request)
    if term is None:
        messages.error(request, 'No term is selected.')
        return redirect(reverse('report_cards:index'))
    try:
        approve_card(student, term, request.user)
    except ValidationError as error:
        for problem in error.messages:
            messages.error(request, problem)
    except PermissionDenied:
        messages.error(request, 'You do not have permission to approve report cards.')
    else:
        messages.success(request, 'Report card approved and frozen.')
    return redirect(_card_url(student, term))


@login_required
@require_capability('approve_report_cards')
@require_POST
def report_card_reopen(request, student_pk):
    student = get_object_or_404(visible_students(request.user), pk=student_pk)
    term = _term(request)
    if term is None:
        messages.error(request, 'No term is selected.')
        return redirect(reverse('report_cards:index'))
    card = get_object_or_404(ReportCard, student=student, term=term)
    try:
        card.reopen(request.POST.get('reason', ''))
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    else:
        messages.success(request, 'Card reopened. Correct the results, then approve again.')
    return redirect(_card_url(student, term))


@login_required
@require_capability('view_grades')
@require_GET
def report_card_print(request, student_pk):
    student = get_object_or_404(visible_students(request.user), pk=student_pk)
    term = _term(request)
    card = get_object_or_404(ReportCard, student=student, term=term)
    if not card.is_frozen:
        raise PermissionDenied('Only an approved card can be printed as final.')
    return HttpResponse(render_card(request, card))