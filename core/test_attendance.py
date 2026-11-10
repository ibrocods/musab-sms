from datetime import date

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .attendance import can_mark, save_register
from .models import AttendanceRecord, AuditLog, SchoolClass, Student, Term


class AttendanceSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'

        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.jss2b = SchoolClass.objects.create(name='JSS2B')

        self.ct = self.make_user('ct', 'Class teacher')
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()
        self.head = self.make_user('hd', 'Head teacher')
        self.readonly = self.make_user('ro', 'Read-only staff')

        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.musa = Student.objects.create(first_name='Musa', last_name='Ali', school_class=self.jss2b)
        self.day = date(2026, 10, 5)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client

    def register_url(self, school_class, day=None):
        url = reverse('attendance_register', args=[school_class.pk])
        return f'{url}?date={(day or self.day).isoformat()}'


class AttendanceRuleTests(AttendanceSetup):
    def test_class_teacher_can_mark_own_class(self):
        self.assertTrue(can_mark(self.ct, self.jss1a))

    def test_class_teacher_cannot_mark_another_class(self):
        self.assertFalse(can_mark(self.ct, self.jss2b))

    def test_head_teacher_cannot_mark(self):
        self.assertFalse(can_mark(self.head, self.jss1a))

    def test_save_register_creates_a_record(self):
        save_register(self.jss1a, self.term, self.day, {self.ada: 'A'}, self.ct)
        record = AttendanceRecord.objects.get(student=self.ada, date=self.day)
        self.assertEqual(record.status, 'A')
        self.assertEqual(record.marked_by, self.ct)

    def test_marking_again_updates_the_same_row(self):
        save_register(self.jss1a, self.term, self.day, {self.ada: 'A'}, self.ct)
        save_register(self.jss1a, self.term, self.day, {self.ada: 'P'}, self.ct)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        self.assertEqual(AttendanceRecord.objects.get().status, 'P')

    def test_blank_clears_the_mark(self):
        save_register(self.jss1a, self.term, self.day, {self.ada: 'L'}, self.ct)
        save_register(self.jss1a, self.term, self.day, {self.ada: None}, self.ct)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_date_outside_the_term_is_refused(self):
        with self.assertRaises(ValidationError):
            save_register(self.jss1a, self.term, date(2027, 1, 5), {self.ada: 'P'}, self.ct)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_student_from_another_class_is_refused(self):
        with self.assertRaises(ValidationError):
            save_register(self.jss1a, self.term, self.day, {self.ada: 'P', self.musa: 'P'}, self.ct)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_one_mark_per_student_per_day_is_enforced(self):
        AttendanceRecord.objects.create(
            student=self.ada, school_class=self.jss1a, term=self.term, date=self.day, status='P',
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceRecord.objects.create(
                student=self.ada, school_class=self.jss1a, term=self.term, date=self.day, status='A',
            )


class AttendanceViewTests(AttendanceSetup):
    def test_class_teacher_saves_through_the_page(self):
        response = self.login(self.ct).post(
            self.register_url(self.jss1a), {f'status_{self.ada.pk}': 'L'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AttendanceRecord.objects.get(student=self.ada).status, 'L')

    def test_class_teacher_cannot_open_another_class(self):
        response = self.login(self.ct).get(self.register_url(self.jss2b))
        self.assertEqual(response.status_code, 404)

    def test_head_teacher_can_view_but_not_post(self):
        client = self.login(self.head)
        self.assertEqual(client.get(self.register_url(self.jss1a)).status_code, 200)
        response = client.post(self.register_url(self.jss1a), {f'status_{self.ada.pk}': 'P'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_read_only_staff_cannot_post(self):
        response = self.login(self.readonly).post(
            self.register_url(self.jss1a), {f'status_{self.ada.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 403)

    def test_unknown_status_code_is_rejected(self):
        response = self.login(self.ct).post(
            self.register_url(self.jss1a), {f'status_{self.ada.pk}': 'Z'},
        )
        self.assertEqual(response.status_code, 400)

    def test_date_outside_term_saves_nothing(self):
        response = self.login(self.ct).post(
            self.register_url(self.jss1a, date(2027, 1, 5)), {f'status_{self.ada.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_anonymous_user_is_sent_to_login(self):
        response = Client().get(self.register_url(self.jss1a))
        self.assertEqual(response.status_code, 302)