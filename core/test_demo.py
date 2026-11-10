import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from .demo import seed_demo, wipe_demo
from .models import SchoolClass, Student, Term


class DemoDataTests(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)

        # Keep the state file in a temporary folder during tests
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
        self.real_user = User.objects.create_user('real_teacher', password='pass12345!')

    def test_seed_creates_demo_records(self):
        seed_demo(students_per_class=3)
        self.assertEqual(Student.objects.filter(is_demo=True).count(), 6)
        self.assertTrue(Term.objects.filter(is_demo=True, is_current=True).exists())
        self.assertTrue(User.objects.filter(username='demo_head').exists())

    def test_wipe_leaves_real_records_untouched(self):
        seed_demo(students_per_class=3)
        wipe_demo()
        self.assertFalse(Student.objects.filter(is_demo=True).exists())
        self.assertFalse(SchoolClass.objects.filter(is_demo=True).exists())
        self.assertFalse(User.objects.filter(username__startswith='demo_').exists())
        self.assertTrue(Student.objects.filter(pk=self.real_student.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.real_user.pk).exists())

    def test_real_current_term_is_restored_after_wipe(self):
        seed_demo(students_per_class=2)
        self.real_term.refresh_from_db()
        self.assertFalse(self.real_term.is_current)
        wipe_demo()
        self.real_term.refresh_from_db()
        self.assertTrue(self.real_term.is_current)

    def test_seeding_twice_does_not_double_the_data(self):
        seed_demo(students_per_class=2)
        seed_demo(students_per_class=2)
        self.assertEqual(Student.objects.filter(is_demo=True).count(), 4)
        self.assertEqual(Term.objects.filter(is_demo=True).count(), 1)