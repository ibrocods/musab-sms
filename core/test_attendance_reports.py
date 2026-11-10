from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import AttendanceRecord, SchoolClass, Student, Term
from .reports import class_average, student_rows


class ReportSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'

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

        self.ct = self.make_user('ct_rep', 'Class teacher')
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()
        self.head = self.make_user('hd_rep', 'Head teacher')

        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.bola = Student.objects.create(first_name='Bola', last_name='Ade', school_class=self.jss1a)
        self.musa = Student.objects.create(first_name='Musa', last_name='Ali', school_class=self.jss2b)

        self.start = date(2026, 10, 5)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client

    def mark(self, student, offset, status, term=None):
        AttendanceRecord.objects.create(
            student=student, school_class=student.school_class, term=term or self.term,
            date=self.start + timedelta(days=offset), status=status,
        )


class PercentageTests(ReportSetup):
    def test_late_counts_as_attended_and_excused_is_not_counted(self):
        # Present 3, Late 1, Absent 1, Excused 1: 4 attended out of 5 countable days
        for offset, status in enumerate(['P', 'P', 'P', 'L', 'A', 'E']):
            self.mark(self.ada, offset, status)
        row = student_rows([self.ada], self.term)[0]
        self.assertEqual(row['marked'], 6)
        self.assertEqual(row['percentage'], Decimal('80.0'))

    def test_student_with_no_records_has_no_percentage(self):
        row = student_rows([self.ada], self.term)[0]
        self.assertEqual(row['marked'], 0)
        self.assertIsNone(row['percentage'])

    def test_all_excused_has_no_percentage(self):
        self.mark(self.ada, 0, 'E')
        self.mark(self.ada, 1, 'E')
        row = student_rows([self.ada], self.term)[0]
        self.assertIsNone(row['percentage'])

    def test_records_from_other_terms_are_ignored(self):
        self.mark(self.ada, 0, 'A')
        self.mark(self.ada, 1, 'A', term=self.other_term)
        row = student_rows([self.ada], self.term)[0]
        self.assertEqual(row['marked'], 1)
        self.assertEqual(row['percentage'], Decimal('0.0'))

    def test_class_average_ignores_students_with_no_countable_days(self):
        self.mark(self.ada, 0, 'P')
        self.mark(self.ada, 1, 'A')  # 50%
        rows = student_rows([self.ada, self.bola], self.term)
        self.assertEqual(class_average(rows), Decimal('50.0'))


class ReportViewTests(ReportSetup):
    def test_head_teacher_sees_the_report(self):
        self.mark(self.ada, 0, 'P')
        response = self.login(self.head).get(
            reverse('attendance_report'), {'term': self.term.pk, 'class': self.jss1a.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 2)

    def test_class_teacher_cannot_report_another_class(self):
        response = self.login(self.ct).get(
            reverse('attendance_report'), {'term': self.term.pk, 'class': self.jss2b.pk},
        )
        self.assertIsNone(response.context['school_class'])
        self.assertEqual(response.context['rows'], [])

    def test_archived_students_are_left_out(self):
        self.bola.is_archived = True
        self.bola.save()
        response = self.login(self.head).get(
            reverse('attendance_report'), {'term': self.term.pk, 'class': self.jss1a.pk},
        )
        names = [row['student'] for row in response.context['rows']]
        self.assertEqual(names, [self.ada])

    def test_anonymous_user_is_sent_to_login(self):
        response = Client().get(reverse('attendance_report'))
        self.assertEqual(response.status_code, 302)

    def test_bad_term_value_does_not_crash(self):
        response = self.login(self.head).get(
            reverse('attendance_report'), {'term': 'abc', 'class': self.jss1a.pk},
        )
        self.assertEqual(response.status_code, 200)


class CsvExportTests(ReportSetup):
    def test_csv_has_header_and_values(self):
        for offset, status in enumerate(['P', 'A']):
            self.mark(self.ada, offset, status)
        response = self.login(self.head).get(
            reverse('attendance_report_csv'), {'term': self.term.pk, 'class': self.jss1a.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        lines = response.content.decode().strip().splitlines()
        self.assertEqual(
            lines[0],
            'Student ID,Last name,First name,Days marked,Present,Absent,Late,Excused,Attendance %',
        )
        ada_line = next(line for line in lines if line.startswith(self.ada.student_id))
        self.assertIn(',50.0', ada_line)

    def test_csv_for_another_class_is_refused(self):
        response = self.login(self.ct).get(
            reverse('attendance_report_csv'), {'term': self.term.pk, 'class': self.jss2b.pk},
        )
        self.assertEqual(response.status_code, 404)

    def test_csv_without_a_term_or_class_is_refused(self):
        response = self.login(self.head).get(reverse('attendance_report_csv'))
        self.assertEqual(response.status_code, 404)