from decimal import Decimal, InvalidOperation

from .models import GradeBand


def grade_for(score):
    """Return the GradeBand that matches a score from 0 to 100.

    Raises ValueError if the score isn't a number in range, or if no bands exist.
    """
    try:
        value = Decimal(str(score))
    except InvalidOperation:
        raise ValueError(f'Score must be a number, got {score!r}.')

    if value < 0 or value > 100:
        raise ValueError('Score must be between 0 and 100.')

    band = GradeBand.objects.filter(min_score__lte=value).order_by('-min_score').first()
    if band is None:
        raise ValueError('No grade bands are set up. Add them in the admin.')
    return band