from django.template.loader import render_to_string

from core.models import SchoolProfile

DEFAULT_LAYOUT = 'default'


def layout_template_name(layout=None):
    """The template path for a layout. Falls back to the default if the chosen one is missing."""
    layout = layout or SchoolProfile.get().report_card_layout or DEFAULT_LAYOUT
    candidate = f'report_cards/layouts/{layout}/card.html'
    try:
        from django.template.loader import get_template
        get_template(candidate)
        return candidate
    except Exception:
        return f'report_cards/layouts/{DEFAULT_LAYOUT}/card.html'


def render_card(request, card):
    """Render a card from its snapshot, using the school's chosen layout."""
    snapshot = card.snapshot or _draft_placeholder(card)
    context = {
        'card': card,
        'snap': snapshot,
        'school': SchoolProfile.get(),
    }
    return render_to_string(layout_template_name(), context, request=request)


def _draft_placeholder(card):
    """A draft has no snapshot yet, so show the student's details and empty figures."""
    student = card.student
    return {
        'student_id': student.student_id,
        'student_name': f'{student.last_name} {student.first_name}',
        'class': student.school_class.name if student.school_class else '-',
        'term': str(card.term),
        'subjects': [],
        'average': None,
        'position': None,
        'attendance': {'marked': 0, 'present': 0, 'absent': 0, 'late': 0, 'excused': 0, 'percentage': None},
        'class_teacher_comment': '',
        'head_teacher_remark': '',
    }