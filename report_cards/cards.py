from .models import ReportCard


def get_or_create_draft(student, term):
    """The card for this student and term, created as a draft if it doesn't exist yet."""
    card, _ = ReportCard.objects.get_or_create(student=student, term=term)
    return card