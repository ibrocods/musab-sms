from report_cards.models import CardPrint, ReportCard, ReportComment


def wipe_report_card_demo():
    """Remove report card records for demo students only.

    Print records protect cards, and cards and comments protect students, so they
    are removed in that order. Queryset deletes skip the model guards on purpose,
    and they match only demo students.
    """
    CardPrint.objects.filter(card__student__is_demo=True).delete()
    ReportComment.objects.filter(student__is_demo=True).delete()
    ReportCard.objects.filter(student__is_demo=True).delete()