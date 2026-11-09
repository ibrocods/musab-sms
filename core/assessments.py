from decimal import Decimal

from django.core.exceptions import ValidationError

from .models import Assessment


def check_weights(subject, term):
    """Raise ValidationError unless the assessment weights for this subject and term total 100."""
    total = sum(
        (a.weight for a in Assessment.objects.filter(subject=subject, term=term)),
        Decimal('0'),
    )
    if total != Decimal('100'):
        raise ValidationError(
            f'Weights for {subject} in {term} add up to {total}. They must total 100.'
        )