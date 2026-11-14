import random
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .discounts import grant_discount
from .models import Discount, FeeItem, Payment
from .payments import record_payment, reverse_payment


def wipe_fee_demo():
    """Remove demo payments, discounts and fee items.

    Reversals point at payments, and payments point at students, so they're removed
    in that order. Queryset deletes skip the model's delete() guard on purpose, and
    they only match records linked to demo students or demo terms.
    """
    Payment.objects.filter(student__is_demo=True, kind='reversal').delete()
    Payment.objects.filter(student__is_demo=True).delete()
    Discount.objects.filter(student__is_demo=True).delete()
    FeeItem.objects.filter(term__is_demo=True).delete()


def seed_fee_demo(term, bursar, head, classes, students):
    """Create demo fees, payments, one reversal and some scholarships."""
    for school_class in classes:
        FeeItem.objects.create(
            name='DEMO Tuition', amount=Decimal('50000'), term=term, school_class=school_class,
        )
    FeeItem.objects.create(name='DEMO PTA levy', amount=Decimal('5000'), term=term)

    rng = random.Random(7)
    paid_on = timezone.localdate() - timedelta(days=5)
    first_payment = None
    for index, student in enumerate(students):
        if index % 3 == 0:
            continue  # every third student hasn't paid anything yet
        payment = record_payment(
            student=student, term=term,
            amount=Decimal(rng.randrange(10, 50) * 1000),
            method=rng.choice(['cash', 'transfer', 'pos']),
            paid_on=paid_on, user=bursar, note='DEMO payment',
        )
        first_payment = first_payment or payment

    if first_payment:
        reverse_payment(first_payment, user=bursar, reason='DEMO reversal example')

    for student in students[::10]:
        grant_discount(
            student=student, term=term, kind='percent', value=Decimal('10'),
            reason='DEMO scholarship', user=head, starts_on=term.start_date,
        )