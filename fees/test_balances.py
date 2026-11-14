from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase

from core.models import SchoolClass, Student, Term

from fees.balances import debtors, student_balance, statement
from fees.models import FeeItem
from fees.payments import record_payment, reverse_payment


class BalanceSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.other_term = Term.objects.create(
            session='2026/2027', term_number=2, name='Second Term',
            start_date=date(2027, 1, 10), end_date=date(2027, 4, 5),
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.jss2b = SchoolClass.objects.create(name='JSS2B')

        self.bursar = User.objects.create_user('bursar_bal', password='pass12345!')
        self.bursar.groups.add(Group.objects.get(name='Bursar'))

        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.bola = Student.objects.create(first_name='Bola', last_name='Ade', school_class=self.jss2b)
        self.no_class = Student.objects.create(first_name='Chidi', last_name='Eze')

        # One fee for everyone, one for JSS1A only
        self.levy = FeeItem.objects.create(name='PTA levy', amount=Decimal('5000'), term=self.term)
        self.tuition = FeeItem.objects.create(
            name='Tuition', amount=Decimal('45000'), term=self.term, school_class=self.jss1a,
        )

    def pay(self, student, amount, term=None):
        return record_payment(
            student=student, term=term or self.term, amount=amount, method='cash',
            paid_on=date(2026, 10, 5), user=self.bursar,
        )

    def everyone(self):
        return Student.objects.all()


class ChargeTests(BalanceSetup):
    def test_all_class_fee_and_class_fee_both_apply(self):
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['charged'], Decimal('50000'))

    def test_class_fee_does_not_apply_to_other_classes(self):
        row = student_balance(self.term, self.bola)
        self.assertEqual(row['charged'], Decimal('5000'))

    def test_student_without_a_class_gets_only_all_class_fees(self):
        row = student_balance(self.term, self.no_class)
        self.assertEqual(row['charged'], Decimal('5000'))

    def test_inactive_fee_is_not_charged(self):
        self.tuition.is_active = False
        self.tuition.save()
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['charged'], Decimal('5000'))

    def test_fees_from_another_term_are_ignored(self):
        FeeItem.objects.create(name='Other', amount=Decimal('9999'), term=self.other_term)
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['charged'], Decimal('50000'))


class PaymentEffectTests(BalanceSetup):
    def test_payment_reduces_the_balance(self):
        self.pay(self.ada, '20000')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['paid'], Decimal('20000'))
        self.assertEqual(row['balance'], Decimal('30000'))

    def test_reversal_puts_the_money_back_on_the_balance(self):
        payment = self.pay(self.ada, '20000')
        reverse_payment(payment, user=self.bursar, reason='Entered twice')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['paid'], Decimal('0'))
        self.assertEqual(row['balance'], Decimal('50000'))

    def test_exact_payment_clears_the_balance(self):
        self.pay(self.ada, '50000')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['balance'], Decimal('0'))
        self.assertEqual(row['status'], 'clear')

    def test_overpayment_is_a_credit_and_not_a_debt(self):
        self.pay(self.ada, '52000')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['balance'], Decimal('-2000'))
        self.assertEqual(row['status'], 'credit')
        self.assertNotIn(self.ada, [r['student'] for r in debtors(self.term, self.everyone())])

    def test_pennies_are_exact(self):
        self.pay(self.ada, '49999.95')
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['balance'], Decimal('0.05'))

    def test_payments_in_another_term_do_not_count(self):
        self.pay(self.ada, '50000', term=self.other_term)
        row = student_balance(self.term, self.ada)
        self.assertEqual(row['paid'], Decimal('0'))
        self.assertEqual(row['balance'], Decimal('50000'))

    def test_balance_is_calculated_not_stored(self):
        field_names = [field.name for field in Student._meta.get_fields()]
        self.assertFalse(any('balance' in name for name in field_names))
        before = student_balance(self.term, self.ada)['balance']
        self.pay(self.ada, '1000')
        after = student_balance(self.term, self.ada)['balance']
        self.assertEqual(after, before - Decimal('1000'))


class DebtorTests(BalanceSetup):
    def test_debtors_lists_only_students_who_owe(self):
        self.pay(self.ada, '50000')
        owing = [row['student'] for row in debtors(self.term, self.everyone())]
        self.assertNotIn(self.ada, owing)
        self.assertIn(self.bola, owing)
        self.assertIn(self.no_class, owing)

    def test_debtors_largest_balance_first(self):
        result = debtors(self.term, self.everyone())
        self.assertEqual(result[0]['student'], self.ada)
        balances = [row['balance'] for row in result]
        self.assertEqual(balances, sorted(balances, reverse=True))

    def test_archived_student_with_a_debt_is_still_listed(self):
        self.bola.is_archived = True
        self.bola.save()
        result = debtors(self.term, self.everyone())
        bola_row = next(row for row in result if row['student'] == self.bola)
        self.assertTrue(bola_row['archived'])

    def test_statement_has_one_row_per_student(self):
        self.assertEqual(len(statement(self.term, self.everyone())), 3)