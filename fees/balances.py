from decimal import Decimal

from django.db.models import Q, Sum

from .discounts import active_discounts
from .models import FeeItem, Payment

ZERO = Decimal('0.00')


def _all_class_total(term):
    """Fees that apply to every class this term."""
    total = (
        FeeItem.objects.filter(term=term, is_active=True, school_class__isnull=True)
        .aggregate(total=Sum('amount'))['total']
    )
    return total or ZERO


def _per_class_totals(term):
    """Class-specific fees this term, as {class_id: total}."""
    rows = (
        FeeItem.objects.filter(term=term, is_active=True, school_class__isnull=False)
        .order_by()
        .values('school_class')
        .annotate(total=Sum('amount'))
    )
    return {row['school_class']: row['total'] for row in rows}


def _net_paid_by_student(term):
    """Payments minus reversals for each student this term, as {student_id: amount}."""
    rows = (
        Payment.objects.filter(term=term)
        .order_by()
        .values('student')
        .annotate(
            paid=Sum('amount', filter=Q(kind='payment')),
            reversed=Sum('amount', filter=Q(kind='reversal')),
        )
    )
    return {
        row['student']: (row['paid'] or ZERO) - (row['reversed'] or ZERO)
        for row in rows
    }


def _discounts_for(term, students, charged_by_student):
    """Discount amount per student.

    Percentage discounts apply to the student's total charges. Fixed discounts
    are subtracted. The total discount can never exceed the charges.
    """
    result = {}
    for student in students:
        charged = charged_by_student.get(student.pk, ZERO)
        total = ZERO
        for discount in active_discounts(student, term):
            if discount.kind == 'percent':
                total += (charged * discount.value / Decimal('100')).quantize(Decimal('0.01'))
            else:
                total += discount.value
        result[student.pk] = min(total, charged)
    return result


def statement(term, students):
    """One row per student: charged, discount, paid and balance.

    Nothing is stored. Each figure is worked out from the fee items, payments,
    reversals and discounts every time it's asked for.
    """
    students = list(students)
    all_classes = _all_class_total(term)
    per_class = _per_class_totals(term)
    net_paid = _net_paid_by_student(term)

    charged_by_student = {
        student.pk: all_classes + per_class.get(student.school_class_id, ZERO)
        for student in students
    }
    discounts = _discounts_for(term, students, charged_by_student)

    rows = []
    for student in students:
        charged = charged_by_student[student.pk]
        discount = discounts.get(student.pk, ZERO)
        paid = net_paid.get(student.pk, ZERO)
        balance = charged - discount - paid

        if balance > 0:
            status = 'owing'
        elif balance < 0:
            status = 'credit'
        else:
            status = 'clear'

        rows.append({
            'student': student,
            'charged': charged,
            'paid': paid,
            'discount': discount,
            'balance': balance,
            'status': status,
            'archived': student.is_archived,
        })
    return rows


def student_balance(term, student):
    """The statement row for one student."""
    return statement(term, [student])[0]


def debtors(term, students):
    """Students who still owe money this term, largest balance first."""
    rows = [row for row in statement(term, students) if row['status'] == 'owing']
    return sorted(rows, key=lambda row: row['balance'], reverse=True)