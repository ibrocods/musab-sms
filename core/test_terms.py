from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import AuditLog, Term
from .terms import current_term


def make_term(number=1, session='2026/2027', **kwargs):
    defaults = {
        'name': f'Term {number}',
        'start_date': date(2026, 9, 1),
        'end_date': date(2026, 12, 15),
    }
    defaults.update(kwargs)
    return Term.objects.create(session=session, term_number=number, **defaults)


class TermTests(TestCase):
    def test_only_one_term_can_be_current(self):
        first = make_term(1, is_current=True)
        second = make_term(2, start_date=date(2027, 1, 10), end_date=date(2027, 4, 5), is_current=True)

        first.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)
        self.assertEqual(Term.objects.filter(is_current=True).count(), 1)

    def test_current_term_helper(self):
        self.assertIsNone(current_term())
        term = make_term(1, is_current=True)
        self.assertEqual(current_term(), term)

    def test_one_term_number_per_session(self):
        make_term(1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_term(1)

    def test_same_term_number_in_a_new_session_is_allowed(self):
        make_term(1, session='2026/2027')
        make_term(1, session='2027/2028', start_date=date(2027, 9, 1), end_date=date(2027, 12, 15))
        self.assertEqual(Term.objects.count(), 2)

    def test_end_must_be_after_start(self):
        term = Term(
            session='2026/2027', term_number=1, name='Bad',
            start_date=date(2026, 12, 15), end_date=date(2026, 9, 1),
        )
        with self.assertRaises(ValidationError):
            term.full_clean()

    def test_session_format_is_checked(self):
        term = Term(
            session='2026-27', term_number=1, name='Bad',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        with self.assertRaises(ValidationError):
            term.full_clean()

    def test_changing_the_current_term_is_logged(self):
        term = make_term(1)
        term.is_current = True
        term.save()
        self.assertTrue(AuditLog.objects.filter(
            model_name='core.term', action='update', object_id=str(term.pk),
        ).exists())