from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import AuditLog, SchoolClass, Student, Term
from fees.balances import student_balance
from fees.discounts import active_discounts, end_discount, grant_discount
from fees.models import Discount, FeeItem
from fees.payments import record_payment


class DiscountSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        FeeItem.objects.create(name='Tuition', amount=Decimal('100000'), term=self.term)

        self.bursar = self.make_user('bursar_disc', 'Bursar')
        self.head = self.make_user('head_disc', 'Head teacher')
        self.teacher = self.make_user('ct_disc', 'Class teacher')

    def make_user(self, username, role):
        user = User.objects.create_user(username, password='pass12345!')
        user.groups.add(Group.objects.get(name=role))
        return user

    def grant(self, kind='percent', value='20', user=None, **kwargs):
        return grant_discount(
            student=self.ada, term=self.term, kind=kind, value=value,
            reason=kwargs.pop('reason', 'Scholarship'), user=user or self.head, **kwargs,
        )


class GrantTests(DiscountSetup):
    def test_head_teacher_can_grant(self):
        discount = self.grant()
        self.assertEqual(discount.approved_by, self.head)

    def test_bursar_can_grant(self):
        discount = self.grant(user=self.bursar)
        self.assertEqual(discount.approved_by, self.bursar)

    def test_class_teacher_cannot_grant(self):
        with self.assertRaises(PermissionDenied):
            self.grant(user=self.teacher)

    def test_reason_is_required(self):
        with self.assertRaises(ValidationError):
            self.grant(reason='   ')

    def test_percentage_above_100_is_refused(self):
        with self.assertRaises(ValidationError):
            self.grant(value='120')

    def test_zero_percentage_is_refused(self):
        with self.assertRaises(ValidationError):
            self.grant(value='0')

    def test_end_before_start_is_refused(self):
        today = date(2026, 10, 1)
        with self.assertRaises(ValidationError):
            self.grant(starts_on=today, ends_on=today - timedelta(days=1))

    def test_granting_is_logged(self):
        discount = self.grant()
        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.discount', action='create', object_id=str(discount.pk),
        ).exists())


class DiscountMathTests(DiscountSetup):
    def test_percentage_applies_to_total_charges(self):
        self.grant(kind='percent', value='20')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['discount'], Decimal('20000.00'))
        self.assertEqual(row['balance'], Decimal('80000.00'))

    def test_fixed_discount_is_subtracted(self):
        self.grant(kind='fixed', value='15000')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['balance'], Decimal('85000.00'))

    def test_discount_cannot_exceed_charges(self):
        self.grant(kind='fixed', value='150000')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['discount'], Decimal('100000.00'))
        self.assertEqual(row['balance'], Decimal('0'))

    def test_discount_then_payment(self):
        self.grant(kind='percent', value='50')
        record_payment(
            student=self.ada, term=self.term, amount='30000', method='cash',
            paid_on=date(2026, 10, 5), user=self.bursar,
        )
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['balance'], Decimal('20000.00'))

    def test_two_discounts_stack_up_to_the_charges(self):
        self.grant(kind='percent', value='50', reason='Scholarship')
        self.grant(kind='fixed', value='60000', reason='Hardship')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['discount'], Decimal('100000.00'))

    def test_discount_from_another_term_does_not_apply(self):
        other = Term.objects.create(
            session='2026/2027', term_number=2, name='Second Term',
            start_date=date(2027, 1, 10), end_date=date(2027, 4, 5),
        )
        grant_discount(
            student=self.ada, term=other, kind='percent', value='50',
            reason='Other term', user=self.head,
        )
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['discount'], Decimal('0'))


class DiscountTimingTests(DiscountSetup):
    def test_discount_starting_in_the_future_does_not_apply_yet(self):
        self.grant(kind='percent', value='50', starts_on=date(2099, 1, 1))
        self.assertEqual(active_discounts(self.ada, self.term, on=date(2026, 10, 1)).count(), 0)

    def test_ended_discount_stops_applying(self):
        discount = self.grant(kind='percent', value='50', starts_on=date(2026, 9, 1))
        end_discount(discount, user=self.head, ends_on=date(2026, 9, 30))
        self.assertEqual(active_discounts(self.ada, self.term, on=date(2026, 10, 1)).count(), 0)
        self.assertEqual(active_discounts(self.ada, self.term, on=date(2026, 9, 15)).count(), 1)

    def test_ending_a_discount_keeps_the_record(self):
        discount = self.grant()
        end_discount(discount, user=self.head)
        self.assertTrue(Discount.objects.filter(pk=discount.pk).exists())

    def test_class_teacher_cannot_end_a_discount(self):
        discount = self.grant()
        with self.assertRaises(PermissionDenied):
            end_discount(discount, user=self.teacher)


class DiscountImmutabilityTests(DiscountSetup):
    def test_discount_cannot_be_deleted(self):
        discount = self.grant()
        with self.assertRaises(PermissionError):
            discount.delete()
        self.assertTrue(Discount.objects.filter(pk=discount.pk).exists())