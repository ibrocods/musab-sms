from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.permissions import can

from .models import Payment

TWO_PLACES = Decimal('0.01')


def _clean_amount(amount):
    try:
        value = Decimal(str(amount))
    except InvalidOperation:
        raise ValidationError('Enter an amount.')
    if value <= 0:
        raise ValidationError('The amount must be more than zero.')
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def record_payment(*, student, term, amount, method, paid_on, user, reference='', note=''):
    """Record money received from a student. Needs the collect_fees capability."""
    if not can(user, 'collect_fees'):
        raise PermissionDenied

    value = _clean_amount(amount)
    if method not in dict(Payment.METHOD_CHOICES):
        raise ValidationError('Choose a payment method.')

    with transaction.atomic():
        return Payment.objects.create(
            student=student,
            term=term,
            amount=value,
            method=method,
            paid_on=paid_on,
            reference=reference.strip(),
            note=note.strip(),
            recorded_by=user,
        )


def reverse_payment(payment, *, user, reason):
    """Cancel a payment by recording an equal reversal. The original is kept.

    Needs the reverse_payments capability and a reason. A payment can be
    reversed only once, and a reversal can't be reversed.
    """
    if not can(user, 'reverse_payments'):
        raise PermissionDenied

    reason = (reason or '').strip()
    if not reason:
        raise ValidationError('Give a reason for the reversal.')
    if payment.kind != 'payment':
        raise ValidationError('Only a payment can be reversed.')
    if Payment.objects.filter(reverses=payment).exists():
        raise ValidationError('This payment has already been reversed.')

    with transaction.atomic():
        return Payment.objects.create(
            student=payment.student,
            term=payment.term,
            kind='reversal',
            amount=payment.amount,
            method=payment.method,
            paid_on=timezone.localdate(),
            reference=payment.reference,
            note=f'Reversal of {payment.receipt_number}: {reason}'[:200],
            reverses=payment,
            recorded_by=user,
        )