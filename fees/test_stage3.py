from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase

from core.models import AuditLog, SchoolClass, Student, Term
from core.permissions import can
from fees.balances import debtors, student_balance
from fees.discounts import grant_discount
from fees.models import FeeItem
from fees.payments import record_payment, reverse_payment

ROLES = [
    'Head teacher', 'Bursar', 'Class teacher', 'Subject teacher',
    'Exams officer', 'Records officer', 'Read-only staff',
]

FEE_CAPS = ['view_fees', 'manage_fees', 'collect_fees', 'reverse_payments', 'grant_discounts']

EXPECTED_FEE_ACCESS = {
    'Head teacher': {'view_fees', 'reverse_payments', 'grant_discounts'},
    'Bursar': {'view_fees', 'manage_fees', 'collect_fees', 'reverse_payments', 'grant_discounts'},
}


class Stage3Setup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        FeeItem.objects.create(
            name='Tuition', amount=Decimal('50000'), term=self.term, school_class=self.jss1a,
        )
        FeeItem.objects.create(name='PTA levy', amount=Decimal('5000'), term=self.term)

        self.bursar = self.make_user('bursar_s3', 'Bursar')
        self.head = self.make_user('head_s3', 'Head teacher')
        self.paid_on = date(2026, 10, 5)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password='pass12345!')
        user.groups.add(Group.objects.get(name=role))
        return user


class MoneyFlowTests(Stage3Setup):
    def test_one_student_from_charge_to_debtor_list(self):
        self.assertEqual(student_balance(self.term, self.ada)['charged'], Decimal('55000'))

        first = record_payment(
            student=self.ada, term=self.term, amount='20000', method='cash',
            paid_on=self.paid_on, user=self.bursar,
        )
        self.assertEqual(student_balance(self.term, self.ada)['balance'], Decimal('35000'))

        grant_discount(
            student=self.ada, term=self.term, kind='percent', value='10',
            reason='Scholarship', user=self.head,
        )
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['discount'], Decimal('5500.00'))
        self.assertEqual(row['balance'], Decimal('29500.00'))

        reverse_payment(first, user=self.bursar, reason='Entered twice')
        self.assertEqual(student_balance(self.term, self.ada)['balance'], Decimal('49500.00'))

        record_payment(
            student=self.ada, term=self.term, amount='30000', method='transfer',
            paid_on=self.paid_on, user=self.bursar,
        )
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['paid'], Decimal('30000'))
        self.assertEqual(row['balance'], Decimal('19500.00'))

        owing = [r['student'] for r in debtors(self.term, Student.objects.all())]
        self.assertIn(self.ada, owing)

    def test_receipts_never_repeat(self):
        first = record_payment(
            student=self.ada, term=self.term, amount='1000', method='cash',
            paid_on=self.paid_on, user=self.bursar,
        )
        reversal = reverse_payment(first, user=self.bursar, reason='Test')
        second = record_payment(
            student=self.ada, term=self.term, amount='1000', method='cash',
            paid_on=self.paid_on, user=self.bursar,
        )
        numbers = {first.receipt_number, reversal.receipt_number, second.receipt_number}
        self.assertEqual(len(numbers), 3)

    def test_every_money_change_is_in_the_audit_log(self):
        payment = record_payment(
            student=self.ada, term=self.term, amount='20000', method='cash',
            paid_on=self.paid_on, user=self.bursar,
        )
        discount = grant_discount(
            student=self.ada, term=self.term, kind='percent', value='10',
            reason='Scholarship', user=self.head,
        )
        reversal = reverse_payment(payment, user=self.bursar, reason='Test')

        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.payment', action='create', object_id=str(payment.pk),
        ).exists())
        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.payment', action='create', object_id=str(reversal.pk),
        ).exists())
        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.discount', action='create', object_id=str(discount.pk),
        ).exists())

    def test_original_payment_is_never_changed(self):
        payment = record_payment(
            student=self.ada, term=self.term, amount='20000', method='cash',
            paid_on=self.paid_on, user=self.bursar,
        )
        reverse_payment(payment, user=self.bursar, reason='Test')
        payment.refresh_from_db()
        self.assertEqual(payment.kind, 'payment')
        self.assertEqual(payment.amount, Decimal('20000.00'))


class RoleAccessTests(Stage3Setup):
    def setUp(self):
        super().setUp()
        self.users = {}
        for role in ROLES:
            username = 'role_' + role.lower().replace(' ', '_')
            self.users[role] = self.make_user(username, role)

    def test_fee_access_matches_the_role_map(self):
        for role in ROLES:
            expected = EXPECTED_FEE_ACCESS.get(role, set())
            granted = {cap for cap in FEE_CAPS if can(self.users[role], cap)}
            self.assertEqual(granted, expected, role)