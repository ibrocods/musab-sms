from core.models import SchoolProfile


def next_receipt_number(year):
    """Return a receipt number that has never been used.

    Reversals are rows too, so they take their own numbers. A number is never
    reused, even after a payment is reversed.

    If the pattern includes {year}, numbering restarts each year. Otherwise it
    runs continuously across years.
    """
    from .models import Payment

    pattern = SchoolProfile.get().receipt_pattern
    if '{seq' not in pattern:
        raise ValueError('The receipt pattern must include {seq}, for example RCPT-{year}-{seq:04d}.')

    if '{year}' in pattern:
        seq = Payment.objects.filter(receipt_year=year).count() + 1
    else:
        seq = Payment.objects.count() + 1

    while True:
        candidate = pattern.format(year=year, seq=seq)
        if not Payment.objects.filter(receipt_number=candidate).exists():
            return candidate
        seq += 1