from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .locking import is_locked, set_lock
from .models import Assessment, AuditLog, ClassSubject, ResultLock, SchoolClass, Score, Student, Subject, Term
from .scoring import save_score


class LockSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'

        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.english = Subject.objects.create(name='English', code='ENG')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')

        self.teacher = self.make_user('maths1', 'Subject teacher')
        self.head = self.make_user('hd1', 'Head teacher')
        self.exams = self.make_user('exams1', 'Exams officer')

        self.maths_link = ClassSubject.objects.create(
            school_class=self.jss1a, subject=self.maths, teacher=self.teacher,
        )
        self.english_link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.english)

        self.maths_exam = Assessment.objects.create(
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


class LockRuleTests(LockSetup):
    def test_head_teacher_can_lock(self):
        set_lock(self.maths_link, self.term, True, self.head)
        self.assertTrue(is_locked(self.maths_link, self.term))

    def test_exams_officer_can_lock(self):
        set_lock(self.maths_link, self.term, True, self.exams)
        self.assertTrue(is_locked(self.maths_link, self.term))

    def test_subject_teacher_cannot_lock(self):
        with self.assertRaises(PermissionDenied):
            set_lock(self.maths_link, self.term, True, self.teacher)
        self.assertFalse(is_locked(self.maths_link, self.term))

    def test_unlock_needs_a_reason(self):
        set_lock(self.maths_link, self.term, True, self.head)
        with self.assertRaises(ValidationError):
            set_lock(self.maths_link, self.term, False, self.head, reason='   ')
        self.assertTrue(is_locked(self.maths_link, self.term))

    def test_unlock_with_a_reason_works(self):
        set_lock(self.maths_link, self.term, True, self.head)
        set_lock(self.maths_link, self.term, False, self.head, reason='Wrong mark on script')
        lock = ResultLock.objects.get(class_subject=self.maths_link, term=self.term)
        self.assertFalse(lock.is_locked)
        self.assertEqual(lock.unlock_reason, 'Wrong mark on script')
        self.assertEqual(lock.unlocked_by, self.head)

    def test_lock_applies_to_one_subject_only(self):
        set_lock(self.maths_link, self.term, True, self.head)
        self.assertFalse(is_locked(self.english_link, self.term))

    def test_locking_and_unlocking_are_logged(self):
        set_lock(self.maths_link, self.term, True, self.head)
        set_lock(self.maths_link, self.term, False, self.head, reason='Correction')
        entries = AuditLog.objects.filter(model_name='core.resultlock', action='update')
        self.assertGreaterEqual(entries.count(), 2)


class LockEnforcementTests(LockSetup):
    def test_save_score_refuses_a_locked_subject(self):
        set_lock(self.maths_link, self.term, True, self.head)
        with self.assertRaises(ValidationError):
            save_score(self.ada, self.maths_exam, Decimal('20'), self.teacher)
        self.assertFalse(Score.objects.exists())

    def test_teacher_post_is_refused_when_locked(self):
        set_lock(self.maths_link, self.term, True, self.head)
        url = reverse('score_entry', args=[self.maths_link.pk, self.maths_exam.pk])
        response = self.login(self.teacher).post(url, {f'score_{self.ada.pk}': '30'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Score.objects.exists())

    def test_teacher_sees_read_only_page_when_locked(self):
        set_lock(self.maths_link, self.term, True, self.head)
        url = reverse('score_entry', args=[self.maths_link.pk, self.maths_exam.pk])
        response = self.login(self.teacher).get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['locked'])

    def test_other_subjects_stay_editable(self):
        set_lock(self.maths_link, self.term, True, self.head)
        english_exam = Assessment.objects.create(
            subject=self.english, term=self.term, name='Exam', weight=100, max_mark=40,
        )
        save_score(self.ada, english_exam, Decimal('25'), self.teacher)
        self.assertTrue(Score.objects.filter(assessment=english_exam).exists())

    def test_teacher_cannot_use_the_lock_view(self):
        url = reverse('result_lock', args=[self.maths_link.pk, self.term.pk])
        response = self.login(self.teacher).post(url, {'action': 'lock'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(is_locked(self.maths_link, self.term))

    def test_head_teacher_can_lock_through_the_view(self):
        url = reverse('result_lock', args=[self.maths_link.pk, self.term.pk])
        response = self.login(self.head).post(url, {'action': 'lock'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(is_locked(self.maths_link, self.term))