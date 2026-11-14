import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase

from core.demo import seed_demo, wipe_demo
from core.models import SchoolClass, Student, Term
from fees.models import Discount, FeeItem, Payment
from fees.payments import record_payment


class DemoFeesTests(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)

        state = Path(tempfile.mkdtemp()) / 'demo_state.json'
        patcher = patch('core.demo.STATE_FILE', state)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.real_term = Term.objects.create(
            session='2026/2027', term_number=1, name='Real Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.real_class = SchoolClass.objects.create(name='REAL JSS1A')
        self.real_student = Student.objects.create(
            first_name='Real', last_name='Pupil', school_class=self.real_class,
        )
        self.real_bursar = User.objects.create_user('real_bursar', password='pass12345!')
        self.real_bursar.groups.add(Group.objects.get(name='Bursar'))
        self.real_payment = record_payment(
            student=self.real_student, term=self.real_term, amount='1000', method='cash',
            paid_on=date(2026, 10, 5), user=self.real_bursar,
        )

    def test_seed_creates_demo_money(self):
        seed_demo(students_per_class=4)
        self.assertTrue(Payment.objects.filter(student__is_demo=True).exists())
        self.assertTrue(Discount.objects.filter(student__is_demo=True).exists())
        self.assertTrue(FeeItem.objects.filter(term__is_demo=True).exists())

    def test_wipe_removes_demo_money_without_errors(self):
        seed_demo(students_per_class=4)
        wipe_demo()  # would raise ProtectedError before this fix
        self.assertFalse(Payment.objects.filter(student__is_demo=True).exists())
        self.assertFalse(Discount.objects.filter(student__is_demo=True).exists())
        self.assertFalse(FeeItem.objects.filter(term__is_demo=True).exists())
        self.assertFalse(User.objects.filter(username__startswith='demo_').exists())

    def test_wipe_keeps_real_payments_and_users(self):
        seed_demo(students_per_class=4)
        wipe_demo()
        self.assertTrue(Payment.objects.filter(pk=self.real_payment.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.real_bursar.pk).exists())

    def test_seed_wipe_seed_again(self):
        seed_demo(students_per_class=2)
        seed_demo(students_per_class=2)
        self.assertEqual(Student.objects.filter(is_demo=True).count(), 4)
        self.assertEqual(Payment.objects.filter(student__is_demo=True, kind='reversal').count(), 1)