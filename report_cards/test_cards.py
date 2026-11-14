from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import AuditLog, SchoolClass, Student, Term
from report_cards.cards import get_or_create_draft
from report_cards.models import ReportCard


class CardSetup(TestCase):
    def setUp(self):
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.snapshot = {'Ada': {'average': '79.50', 'position': 1}}


class DraftTests(CardSetup):
    def test_new_card_starts_as_draft(self):
        card = get_or_create_draft(self.ada, self.term)
        self.assertEqual(card.status, 'draft')
        self.assertIsNone(card.snapshot)
        self.assertFalse(card.is_frozen)

    def test_asking_twice_returns_the_same_card(self):
        first = get_or_create_draft(self.ada, self.term)
        second = get_or_create_draft(self.ada, self.term)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ReportCard.objects.count(), 1)

    def test_one_card_per_student_per_term(self):
        ReportCard.objects.create(student=self.ada, term=self.term)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReportCard.objects.create(student=self.ada, term=self.term)

    def test_draft_can_still_be_saved(self):
        card = get_or_create_draft(self.ada, self.term)
        card.save()
        self.assertEqual(card.status, 'draft')


class FreezeTests(CardSetup):
    def test_freeze_stores_the_snapshot_and_approver(self):
        card = get_or_create_draft(self.ada, self.term)
        card.freeze(self.snapshot, user=None)
        card.refresh_from_db()
        self.assertEqual(card.status, 'approved')
        self.assertEqual(card.snapshot, self.snapshot)
        self.assertIsNotNone(card.approved_at)

    def test_frozen_card_cannot_be_saved_normally(self):
        card = get_or_create_draft(self.ada, self.term)
        card.freeze(self.snapshot, user=None)
        card.reopen_reason = 'Sneaky edit'
        with self.assertRaises(PermissionError):
            card.save()

    def test_frozen_snapshot_cannot_be_changed_directly(self):
        card = get_or_create_draft(self.ada, self.term)
        card.freeze(self.snapshot, user=None)
        card.snapshot = {'Ada': {'average': '99.00'}}
        with self.assertRaises(PermissionError):
            card.save()
        card.refresh_from_db()
        self.assertEqual(card.snapshot, self.snapshot)

    def test_stale_copy_cannot_overwrite_a_frozen_card(self):
        card = get_or_create_draft(self.ada, self.term)
        stale = ReportCard.objects.get(pk=card.pk)
        card.freeze(self.snapshot, user=None)
        stale.snapshot = {'stale': True}
        with self.assertRaises(PermissionError):
            stale.save()

    def test_freezing_twice_is_refused(self):
        card = get_or_create_draft(self.ada, self.term)
        card.freeze(self.snapshot, user=None)
        with self.assertRaises(ValidationError):
            card.freeze(self.snapshot, user=None)

    def test_frozen_card_cannot_be_deleted(self):
        card = get_or_create_draft(self.ada, self.term)
        card.freeze(self.snapshot, user=None)
        with self.assertRaises(PermissionError):
            card.delete()
        self.assertTrue(ReportCard.objects.filter(pk=card.pk).exists())

    def test_draft_cannot_be_deleted_either(self):
        card = get_or_create_draft(self.ada, self.term)
        with self.assertRaises(PermissionError):
            card.delete()

    def test_freeze_is_logged(self):
        card = get_or_create_draft(self.ada, self.term)
        card.freeze(self.snapshot, user=None)
        entry = AuditLog.objects.filter(
            model_name='report_cards.reportcard', action='update', object_id=str(card.pk),
        ).latest('pk')
        self.assertEqual(entry.changes['status'], ['draft', 'approved'])


class ReopenTests(CardSetup):
    def approved_card(self):
        card = get_or_create_draft(self.ada, self.term)
        card.freeze(self.snapshot, user=None)
        return card

    def test_reopen_returns_the_card_to_draft(self):
        card = self.approved_card()
        card.reopen('Wrong mark on script')
        card.refresh_from_db()
        self.assertEqual(card.status, 'draft')
        self.assertIsNone(card.snapshot)
        self.assertEqual(card.reopen_reason, 'Wrong mark on script')

    def test_reopened_card_can_be_saved_and_frozen_again(self):
        card = self.approved_card()
        card.reopen('Correction')
        card.freeze({'Ada': {'average': '81.00'}}, user=None)
        card.refresh_from_db()
        self.assertEqual(card.snapshot, {'Ada': {'average': '81.00'}})

    def test_reopen_needs_a_reason(self):
        card = self.approved_card()
        with self.assertRaises(ValidationError):
            card.reopen('   ')
        card.refresh_from_db()
        self.assertEqual(card.status, 'approved')

    def test_draft_cannot_be_reopened(self):
        card = get_or_create_draft(self.ada, self.term)
        with self.assertRaises(ValidationError):
            card.reopen('Not approved')

    def test_reopen_is_logged(self):
        card = self.approved_card()
        card.reopen('Correction')
        self.assertTrue(AuditLog.objects.filter(
            model_name='report_cards.reportcard', object_id=str(card.pk),
            action='update', changes__status__0='approved',
        ).exists() or AuditLog.objects.filter(
            model_name='report_cards.reportcard', object_id=str(card.pk), action='update',
        ).latest('pk').changes.get('status') == ['approved', 'draft'])