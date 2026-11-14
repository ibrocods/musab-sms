from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.db import models
from core.permissions import can

from .models import Discount


def grant_discount(*, student, term, kind, value, reason, user, starts_on=None, ends_on=None):
    """Create a discount. Needs the grant_discounts capability and a reason."""
    if not can(user, 'grant_discounts'):
        raise PermissionDenied

    reason = (reason or '').strip()
    if not reason:
        raise ValidationError('Give a reason for the discount.')
    if kind not in dict(Discount.KIND_CHOICES):
        raise ValidationError('Choose a discount type.')

    try:
        amount = Decimal(str(value))
    except Exception:
        raise ValidationError('Enter a number for the discount.')

    discount = Discount(
        student=student,
        term=term,
        kind=kind,
        value=amount,
        reason=reason,
        starts_on=starts_on or timezone.localdate(),
        ends_on=ends_on,
    )
    discount.full_clean()

    with transaction.atomic():
        discount.approved_by = user
        discount.save()
    return discount


def end_discount(discount, *, user, ends_on=None):
    """Stop a discount from a given date. The record is kept."""
    if not can(user, 'grant_discounts'):
        raise PermissionDenied
    discount.ends_on = ends_on or timezone.localdate()
    discount.save()
    return discount


def active_discounts(student, term, on=None):
    """Discounts that apply to this student in this term on a given day."""
    day = on or timezone.localdate()
    return Discount.objects.filter(
        student=student, term=term, starts_on__lte=day,
    ).filter(
        models.Q(ends_on__isnull=True) | models.Q(ends_on__gte=day),
    )