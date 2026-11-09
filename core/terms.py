from .models import Term


def current_term():
    """Return the term marked as current, or None if none is set."""
    return Term.objects.filter(is_current=True).first()