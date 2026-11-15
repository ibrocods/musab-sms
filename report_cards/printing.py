from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models import SchoolProfile
from core.permissions import can

from .models import CardPrint


def record_print(card, user):
    """Log one printed copy of an approved card and return its copy number."""
    if not can(user, 'print_report_cards'):
        raise PermissionDenied
    if not card.is_frozen:
        raise ValidationError('Only an approved report card can be printed as final.')

    with transaction.atomic():
        copy_number = card.prints.count() + 1
        CardPrint.objects.create(
            card=card,
            copy_number=copy_number,
            layout=SchoolProfile.get().report_card_layout,
            printed_by=user,
        )
    return copy_number