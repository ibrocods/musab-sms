from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .attendance import save_register
from .locking import is_locked, set_lock
from .models import (
    Assessment, AttendanceRecord, AuditLog, ClassSubject, ResultLock,
    SchoolClass, Score, Student, Subject, Term,
)
from .reports import student_rows
from .scoring import grade_for_score, save_score


class Stage2EndToEnd(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'

        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')

        self.class_teacher = self.make_user('ct_e2e', 'Class teacher')
        self.jss1a.class_teacher = self.class_teacher
        self.jss1a.save()
        self.maths_teacher = self.make_user('maths_e2e', 'Subject teacher')
        self.head = self.make_user('hd_e2e', 'Head teacher')

        self.maths_link = ClassSubject.objects.create(
            school_class=self.jss1a, subject=self.maths, teacher=self.maths_teacher,
        )
        self.exam = Assessment.objects.create(
            subject=self.maths, term=self.term, name='Exam', weight=100, max_mark=40,
        )
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client

    def test_scores_grade_and_audit(self):
        # 35 out of 40 is 87.5%, which is an A under the default bands
        save_score(self.ada, self.exam, Decimal('35'), self.maths_teacher)
        score = Score.objects.get(student=self.ada, assessment=self.exam)
        self.assertEqual(grade_for_score(score).grade, 'A')
        self.assertTrue(AuditLog.objects.filter(model_name='core.score', action='create').exists())

    def test_attendance_report_matches_the_register(self):
        # Three school days: Monday, Tuesday, Wednesday
        days = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
        statuses = ['P', 'P', 'A']
        for day, status in zip(days, statuses):
            save_register(self.jss1a, self.term, day, {self.ada: status}, self.class_teacher)

        row = student_rows([self.ada], self.term)[0]
        self.assertEqual(row['marked'], 3)
        self.assertEqual(row['present'], 2)
        self.assertEqual(row['absent'], 1)
        self.assertEqual(row['percentage'], Decimal('66.7'))

    def test_register_audit_entry_is_summarised(self):
        save_register(self.jss1a, self.term, date(2026, 10, 5), {self.ada: 'A'}, self.class_teacher)
        entry = AuditLog.objects.filter(model_name='core.attendancerecord').latest('pk')
        self.assertIn(self.ada.student_id, entry.changes)

    def test_lock_blocks_teachers_and_unlock_needs_a_reason(self):
        save_score(self.ada, self.exam, Decimal('30'), self.maths_teacher)

        set_lock(self.maths_link, self.term, True, self.head)
        self.assertTrue(is_locked(self.maths_link, self.term))

        with self.assertRaises(ValidationError):
            save_score(self.ada, self.exam, Decimal('20'), self.maths_teacher)
        self.assertEqual(Score.objects.get(student=self.ada).score, Decimal('30'))

        with self.assertRaises(ValidationError):
            set_lock(self.maths_link, self.term, False, self.head, reason='')

        set_lock(self.maths_link, self.term, False, self.head, reason='Wrong mark on script')
        self.assertFalse(is_locked(self.maths_link, self.term))
        save_score(self.ada, self.exam, Decimal('32'), self.maths_teacher)
        self.assertEqual(Score.objects.get(student=self.ada).score, Decimal('32'))

    def test_only_lock_holders_can_lock(self):
        with self.assertRaises(PermissionDenied):
            set_lock(self.maths_link, self.term, True, self.maths_teacher)
        with self.assertRaises(PermissionDenied):
            set_lock(self.maths_link, self.term, True, self.class_teacher)

    def test_lock_and_unlock_are_recorded(self):
        set_lock(self.maths_link, self.term, True, self.head)
        set_lock(self.maths_link, self.term, False, self.head, reason='Correction')
        lock = ResultLock.objects.get(class_subject=self.maths_link, term=self.term)
        self.assertEqual(lock.locked_by, self.head)
        self.assertEqual(lock.unlocked_by, self.head)
        self.assertEqual(lock.unlock_reason, 'Correction')

    def test_weekend_register_is_refused_end_to_end(self):
        with self.assertRaises(ValidationError):
            save_register(self.jss1a, self.term, date(2026, 10, 10), {self.ada: 'P'}, self.class_teacher)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_pages_load_for_the_right_roles(self):
        head = self.login(self.head)
        self.assertEqual(head.get(reverse('student_list')).status_code, 200)
        self.assertEqual(head.get(reverse('attendance_report'), {'term': self.term.pk, 'class': self.jss1a.pk}).status_code, 200)

        teacher = self.login(self.maths_teacher)
        self.assertEqual(teacher.get(reverse('score_index')).status_code, 200)
        self.assertEqual(teacher.get(reverse('attendance_index')).status_code, 403)

    def test_head_teacher_cannot_enter_scores_directly(self):
        url = reverse('score_entry', args=[self.maths_link.pk, self.exam.pk])
        response = self.login(self.head).get(url)
        self.assertEqual(response.status_code, 403)