from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from core.attendance import non_school_reason
from core.locking import is_locked
from core.models import AttendanceRecord, ClassSubject
from core.permissions import can
from core.scope import visible_classes, visible_students
from fees.balances import debtors
from fees.models import Payment
from report_cards.models import ReportCard, ReportComment

ZERO = Decimal('0.00')


def _stat(label, value, icon, tone='neutral', hint=''):
    return {'label': label, 'value': value, 'icon': icon, 'tone': tone, 'hint': hint}


def _tile(label, url, icon):
    return {'label': label, 'url': url, 'icon': icon}


def _attention(title, detail, url, tone='warning'):
    return {'title': title, 'detail': detail, 'url': url, 'tone': tone}


def _money(amount):
    return f'₦{amount:,.2f}'


def _unlocked_subjects(user, term):
    locked = ClassSubject.objects.none()
    from core.models import ResultLock
    locked_ids = ResultLock.objects.filter(term=term, is_locked=True).values_list('class_subject_id', flat=True)
    return (
        ClassSubject.objects.filter(school_class__in=visible_classes(user))
        .exclude(pk__in=locked_ids)
        .select_related('school_class', 'subject')
    )


def build_dashboard(user, term):
    """Everything a dashboard shows for this user, worked out from their capabilities."""
    today = timezone.localdate()
    data = {'stats': [], 'attention': [], 'quick': [], 'debtors': []}

    if term is None:
        data['attention'].append(_attention(
            'No current term', 'Ask the administrator to mark a term as current.', None, 'danger',
        ))
        return data

    students = visible_students(user).filter(is_archived=False)
    school_day = non_school_reason(today) is None

    # Students
    if can(user, 'view_students'):
        data['stats'].append(_stat('Students', students.count(), 'bi-people', 'primary', 'In your scope'))
        data['quick'].append(_tile('Students', reverse('student_list'), 'bi-people'))
    if can(user, 'manage_students'):
        data['quick'].append(_tile('Add student', reverse('student_create'), 'bi-person-plus'))

    # Attendance
    if can(user, 'view_attendance') and school_day:
        marks = AttendanceRecord.objects.filter(date=today, school_class__in=visible_classes(user))
        total = marks.count()
        attended = marks.filter(status__in=['P', 'L']).count()
        value = f'{round(attended * 100 / total)}%' if total else '-'
        hint = f'{total} marks today' if total else 'No register marked yet'
        data['stats'].append(_stat('Attendance today', value, 'bi-calendar-check', 'accent', hint))

    if can(user, 'mark_attendance') and school_day:
        for school_class in visible_classes(user).filter(is_active=True):
            if not AttendanceRecord.objects.filter(school_class=school_class, date=today).exists():
                data['attention'].append(_attention(
                    f'Register not marked: {school_class.name}',
                    "Mark today's attendance.",
                    reverse('attendance_register', args=[school_class.pk]),
                    'warning',
                ))
        data['quick'].append(_tile('Mark register', reverse('attendance_index'), 'bi-calendar-check'))

    # Scores
    if can(user, 'enter_grades') or can(user, 'lock_results'):
        data['quick'].append(_tile('Scores', reverse('score_index'), 'bi-pencil-square'))

    if can(user, 'lock_results'):
        for link in _unlocked_subjects(user, term)[:5]:
            data['attention'].append(_attention(
                f'{link.subject.name}: {link.school_class.name}',
                'Results not locked yet',
                reverse('score_index'),
                'warning',
            ))

    if can(user, 'enter_grades'):
        mine = list(ClassSubject.objects.filter(teacher=user).select_related('school_class', 'subject'))
        data['stats'].append(_stat('My subjects', len(mine), 'bi-journal-bookmark', 'accent', 'Subjects you teach'))
        open_links = [link for link in mine if not is_locked(link, term)]
        for link in open_links[:5]:
            data['attention'].append(_attention(
                f'Enter marks: {link.subject.name}, {link.school_class.name}',
                "Enter this term's scores",
                reverse('score_index'),
                'info',
            ))

    # Report cards
    if can(user, 'approve_report_cards'):
        drafts = ReportCard.objects.filter(term=term, student__in=students, status='draft').count()
        if drafts:
            data['attention'].append(_attention(
                f'{drafts} report cards not approved',
                'Approve each card once its results are locked.',
                reverse('report_cards:index'),
                'warning',
            ))
        data['quick'].append(_tile('Approve cards', reverse('report_cards:index'), 'bi-patch-check'))
    elif can(user, 'view_grades'):
        data['quick'].append(_tile('Report cards', reverse('report_cards:index'), 'bi-card-checklist'))

    if can(user, 'write_class_comment'):
        written = ReportComment.objects.filter(
            term=term, kind='class_teacher', student__in=students,
        ).values_list('student_id', flat=True)
        missing = students.exclude(pk__in=written).count()
        if missing:
            data['attention'].append(_attention(
                f'{missing} class comments to write',
                'Write a progress comment for each student in your class.',
                reverse('report_cards:index'),
                'info',
            ))

    # Fees
    if can(user, 'view_fees'):
        paid_today = Payment.objects.filter(term=term, paid_on=today, student__in=students)
        payments = paid_today.filter(kind='payment').aggregate(t=Sum('amount'))['t'] or ZERO
        reversals = paid_today.filter(kind='reversal').aggregate(t=Sum('amount'))['t'] or ZERO
        data['stats'].append(_stat(
            'Collected today', _money(payments - reversals), 'bi-cash-stack', 'accent', 'Payments less reversals',
        ))

        rows = debtors(term, students)
        owed = sum((row['balance'] for row in rows), ZERO)
        data['stats'].append(_stat(
            'Outstanding', _money(owed), 'bi-exclamation-circle', 'neutral', f'{len(rows)} students owing',
        ))
        data['debtors'] = rows[:5]
        if rows:
            data['attention'].append(_attention(
                f'{len(rows)} students owing fees',
                'The largest balances are listed below.',
                reverse('fees:debtors'),
                'danger',
            ))
        data['quick'].append(_tile('Debtors', reverse('fees:debtors'), 'bi-exclamation-circle'))

    if can(user, 'collect_fees'):
        data['quick'].append(_tile('Record payment', reverse('fees:index'), 'bi-wallet2'))
    if can(user, 'manage_fees'):
        data['quick'].append(_tile('Fee setup', reverse('fees:setup'), 'bi-sliders'))
    if can(user, 'manage_staff'):
        data['quick'].append(_tile('Staff', reverse('school_admin:staff_list'), 'bi-person-gear'))
    # Tidy up: no duplicate tiles, at most six, and the most urgent items first
    seen, unique = set(), []
    for tile in data['quick']:
        if tile['url'] not in seen:
            seen.add(tile['url'])
            unique.append(tile)
    data['quick'] = unique[:6]

    severity = {'danger': 0, 'warning': 1, 'info': 2}
    data['attention'].sort(key=lambda item: severity.get(item['tone'], 3))
    return data