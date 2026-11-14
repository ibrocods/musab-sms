from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import AuditLog, SchoolClass, SchoolProfile, Student, Term
from fees.models import Payment
from fees.payments import record_payment, reverse_payment


class PaymentSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.bursar = self.make_user('bursar_pay', 'Bursar')
        self.head = self.make_user('head_pay', 'Head teacher')
        self.teacher = self.make_user('ct_pay', 'Class teacher')
        self.paid_on = date(2026, 10, 5)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def pay(self, amount='5000', user=None):
        return record_payment(
            student=self.ada, term=self.term, amount=amount, method='cash',
            paid_on=self.paid_on, user=user or self.bursar,
        )


class ReceiptTests(PaymentSetup):
    def test_first_receipt_follows_the_default_pattern(self):
        payment = self.pay()
        self.assertEqual(payment.receipt_number, 'RCPT-2026-0001')
        self.assertEqual(payment.receipt_year, 2026)

    def test_receipts_count_up(self):
        first = self.pay()
        second = self.pay()
        self.assertEqual(first.receipt_number, 'RCPT-2026-0001')
        self.assertEqual(second.receipt_number, 'RCPT-2026-0002')

    def test_reversal_takes_its_own_receipt_number(self):
        original = self.pay()
        reversal = reverse_payment(original, user=self.bursar, reason='Entered twice')
        self.assertNotEqual(original.receipt_number, reversal.receipt_number)
        later = self.pay()
        numbers = [original.receipt_number, reversal.receipt_number, later.receipt_number]
        self.assertEqual(len(set(numbers)), 3)

    def test_changing_the_pattern_affects_new_receipts_only(self):
        first = self.pay()
        profile = SchoolProfile.get()
        profile.receipt_pattern = 'SCH-{year}-{seq:05d}'
        profile.save()
        second = self.pay()
        self.assertEqual(first.receipt_number, 'RCPT-2026-0001')
        self.assertEqual(second.receipt_number, 'SCH-2026-00002')

    def test_pattern_without_year_numbers_across_years(self):
        profile = SchoolProfile.get()
        profile.receipt_pattern = 'R-{seq:03d}'
        profile.save()
        in_2026 = self.pay()
        in_2027 = record_payment(
            student=self.ada, term=self.term, amount='5000', method='cash',
            paid_on=date(2027, 2, 1), user=self.bursar,
        )
        self.assertEqual(in_2026.receipt_number, 'R-001')
        self.assertEqual(in_2027.receipt_number, 'R-002')

    def test_pattern_without_sequence_is_refused_in_the_admin(self):
        profile = SchoolProfile.get()
        profile.receipt_pattern = 'RCPT-{year}'
        with self.assertRaises(ValidationError):
            profile.full_clean()


class PaymentRecordingTests(PaymentSetup):
    def test_bursar_can_record_a_payment(self):
        payment = self.pay()
        self.assertEqual(payment.kind, 'payment')
        self.assertEqual(payment.recorded_by, self.bursar)

    def test_amount_is_rounded_to_kobo(self):
        payment = self.pay(amount='100.555')
        self.assertEqual(payment.amount, Decimal('100.56'))

    def test_zero_amount_is_refused(self):
        with self.assertRaises(ValidationError):
            self.pay(amount='0')
        self.assertFalse(Payment.objects.exists())

    def test_negative_amount_is_refused(self):
        with self.assertRaises(ValidationError):
            self.pay(amount='-500')

    def test_text_amount_is_refused(self):
        with self.assertRaises(ValidationError):
            self.pay(amount='five thousand')

    def test_unknown_method_is_refused(self):
        with self.assertRaises(ValidationError):
            record_payment(
                student=self.ada, term=self.term, amount='100', method='bitcoin',
                paid_on=self.paid_on, user=self.bursar,
            )

    def test_head_teacher_cannot_record_a_payment(self):
        with self.assertRaises(PermissionDenied):
            self.pay(user=self.head)

    def test_class_teacher_cannot_record_a_payment(self):
        with self.assertRaises(PermissionDenied):
            self.pay(user=self.teacher)


class PaymentImmutabilityTests(PaymentSetup):
    def test_payment_cannot_be_edited(self):
        payment = self.pay()
        payment.amount = Decimal('1')
        with self.assertRaises(PermissionError):
            payment.save()

    def test_payment_cannot_be_deleted(self):
        payment = self.pay()
        with self.assertRaises(PermissionError):
            payment.delete()
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_payment_creation_is_logged(self):
        payment = self.pay()
        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.payment', action='create', object_id=str(payment.pk),
        ).exists())


class ReversalTests(PaymentSetup):
    def test_bursar_can_reverse(self):
        original = self.pay()
        reversal = reverse_payment(original, user=self.bursar, reason='Wrong student')
        self.assertEqual(reversal.kind, 'reversal')
        self.assertEqual(reversal.reverses, original)
        self.assertEqual(reversal.amount, original.amount)

    def test_head_teacher_can_reverse(self):
        original = self.pay()
        reversal = reverse_payment(original, user=self.head, reason='Approved correction')
        self.assertEqual(reversal.recorded_by, self.head)

    def test_class_teacher_cannot_reverse(self):
        original = self.pay()
        with self.assertRaises(PermissionDenied):
            reverse_payment(original, user=self.teacher, reason='Trying')

    def test_reason_is_required(self):
        original = self.pay()
        with self.assertRaises(ValidationError):
            reverse_payment(original, user=self.bursar, reason='   ')

    def test_payment_can_only_be_reversed_once(self):
        original = self.pay()
        reverse_payment(original, user=self.bursar, reason='First')
        with self.assertRaises(ValidationError):
            reverse_payment(original, user=self.bursar, reason='Second')

    def test_reversal_cannot_be_reversed(self):
        original = self.pay()
        reversal = reverse_payment(original, user=self.bursar, reason='Undo')
        with self.assertRaises(ValidationError):
            reverse_payment(reversal, user=self.bursar, reason='Undo the undo')

    def test_reversal_note_records_the_reason(self):
        original = self.pay()
        reversal = reverse_payment(original, user=self.bursar, reason='Entered twice')
        self.assertIn('Entered twice', reversal.note)
        self.assertIn(original.receipt_number, reversal.note)

    def test_original_payment_is_kept_after_reversal(self):
        original = self.pay()
        reverse_payment(original, user=self.bursar, reason='Test')
        original.refresh_from_db()
        self.assertEqual(original.kind, 'payment')

    def test_reversal_is_logged(self):
        original = self.pay()
        reversal = reverse_payment(original, user=self.bursar, reason='Test')
        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.payment', action='create', object_id=str(reversal.pk),
        ).exists())