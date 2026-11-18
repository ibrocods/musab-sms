from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from core.locking import set_lock
from core.models import Assessment, AuditLog, ClassSubject, SchoolClass, Score, Student, Subject, Term


class SetupBase(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        self.admin = self.make_user('admin_setup', 'School administrator')
        self.head = self.make_user('head_setup', 'Head teacher')
        self.subject_teacher = self.make_user('st_setup', 'Subject teacher')
        self.class_teacher = self.make_user('ct_setup', 'Class teacher')

        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.english = Subject.objects.create(name='English', code='ENG')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.maths)
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client


class SetupAccessTests(SetupBase):
    def test_head_teacher_cannot_open_setup(self):
        response = self.login(self.head).get(reverse('school_admin:setup_home'))
        self.assertEqual(response.status_code, 403)

    def test_subject_teacher_cannot_open_setup(self):
        response = self.login(self.subject_teacher).get(reverse('school_admin:subject_list'))
        self.assertEqual(response.status_code, 403)

    def test_administrator_opens_setup_pages(self):
        client = self.login(self.admin)
        for name in ['setup_home', 'subject_list', 'class_list']:
            self.assertEqual(client.get(reverse(f'school_admin:{name}')).status_code, 200, name)


class SubjectSetupTests(SetupBase):
    def test_administrator_adds_a_subject(self):
        self.login(self.admin).post(reverse('school_admin:subject_create'), {
            'name': 'Biology', 'code': 'BIO', 'is_active': 'on',
        })
        self.assertTrue(Subject.objects.filter(name='Biology').exists())

    def test_duplicate_subject_name_is_refused(self):
        response = self.login(self.admin).post(reverse('school_admin:subject_create'), {
            'name': 'Mathematics', 'code': 'X', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subject.objects.filter(name='Mathematics').count(), 1)

    def test_subject_can_be_deactivated(self):
        self.login(self.admin).post(reverse('school_admin:subject_toggle', args=[self.english.pk]))
        self.english.refresh_from_db()
        self.assertFalse(self.english.is_active)

    def test_subject_creation_is_logged(self):
        self.login(self.admin).post(reverse('school_admin:subject_create'), {
            'name': 'Biology', 'code': 'BIO', 'is_active': 'on',
        })
        subject = Subject.objects.get(name='Biology')
        self.assertTrue(AuditLog.objects.filter(
            model_name='core.subject', action='create', object_id=str(subject.pk),
        ).exists())


class ClassSetupTests(SetupBase):
    def test_administrator_adds_a_class(self):
        self.login(self.admin).post(reverse('school_admin:class_create'), {
            'name': 'JSS2B', 'level': 'JSS2', 'stream': '', 'class_teacher': '', 'is_active': 'on',
        })
        self.assertTrue(SchoolClass.objects.filter(name='JSS2B').exists())

    def test_class_teacher_can_be_set_through_edit(self):
        self.login(self.admin).post(reverse('school_admin:class_edit', args=[self.jss1a.pk]), {
            'name': 'JSS1A', 'level': '', 'stream': '',
            'class_teacher': self.class_teacher.pk, 'is_active': 'on',
        })
        self.jss1a.refresh_from_db()
        self.assertEqual(self.jss1a.class_teacher, self.class_teacher)

    def test_deactivating_a_class_keeps_its_students(self):
        self.login(self.admin).post(reverse('school_admin:class_toggle', args=[self.jss1a.pk]))
        self.jss1a.refresh_from_db()
        self.assertFalse(self.jss1a.is_active)
        self.assertTrue(Student.objects.filter(pk=self.ada.pk, school_class=self.jss1a).exists())


class ClassSubjectSetupTests(SetupBase):
    def test_administrator_adds_a_subject_to_a_class(self):
        self.login(self.admin).post(reverse('school_admin:class_subject_add', args=[self.jss1a.pk]), {
            'subject': self.english.pk, 'teacher': '',
        })
        self.assertTrue(ClassSubject.objects.filter(school_class=self.jss1a, subject=self.english).exists())

    def test_same_subject_twice_in_a_class_is_refused(self):
        self.login(self.admin).post(reverse('school_admin:class_subject_add', args=[self.jss1a.pk]), {
            'subject': self.maths.pk, 'teacher': '',
        })
        self.assertEqual(ClassSubject.objects.filter(school_class=self.jss1a, subject=self.maths).count(), 1)

    def test_subject_without_marks_can_be_removed(self):
        self.login(self.admin).post(reverse('school_admin:class_subject_remove', args=[self.link.pk]))
        self.assertFalse(ClassSubject.objects.filter(pk=self.link.pk).exists())

    def test_subject_with_marks_cannot_be_removed(self):
        assessment = Assessment.objects.create(
            subject=self.maths, term=self.term, name='Exam', weight=100, max_mark=100,
        )
        Score.objects.create(student=self.ada, assessment=assessment, score=Decimal('50'))
        self.login(self.admin).post(reverse('school_admin:class_subject_remove', args=[self.link.pk]))
        self.assertTrue(ClassSubject.objects.filter(pk=self.link.pk).exists())

    def test_subject_with_locked_results_cannot_be_removed(self):
        set_lock(self.link, self.term, True, self.head)
        self.login(self.admin).post(reverse('school_admin:class_subject_remove', args=[self.link.pk]))
        self.assertTrue(ClassSubject.objects.filter(pk=self.link.pk).exists())