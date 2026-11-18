from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from core.models import AuditLog, ClassSubject, SchoolClass, Subject


class StaffSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        self.admin = self.make_user('admin_staff', 'School administrator')
        self.head = self.make_user('head_staff', 'Head teacher')

        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.english = Subject.objects.create(name='English', code='ENG')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.jss2b = SchoolClass.objects.create(name='JSS2B')
        self.maths_link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.maths)
        self.english_link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.english)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client

    def form_data(self, **overrides):
        data = {
            'first_name': 'New', 'last_name': 'Staff', 'username': 'newstaff', 'email': '',
            'role': 'Class teacher', 'class_led': '', 'teaching': [],
        }
        data.update(overrides)
        return data

    def create(self, client, **overrides):
        return client.post(reverse('school_admin:staff_create'), self.form_data(**overrides))


class StaffAccessTests(StaffSetup):
    def test_head_teacher_cannot_open_the_staff_list(self):
        response = self.login(self.head).get(reverse('school_admin:staff_list'))
        self.assertEqual(response.status_code, 403)

    def test_administrator_opens_the_list_and_form(self):
        client = self.login(self.admin)
        self.assertEqual(client.get(reverse('school_admin:staff_list')).status_code, 200)
        self.assertEqual(client.get(reverse('school_admin:staff_create')).status_code, 200)


class StaffCreateTests(StaffSetup):
    def test_class_teacher_is_given_their_class(self):
        self.create(self.login(self.admin), role='Class teacher', class_led=self.jss1a.pk)
        user = User.objects.get(username='newstaff')
        self.jss1a.refresh_from_db()
        self.assertEqual(self.jss1a.class_teacher, user)
        self.assertTrue(user.groups.filter(name='Class teacher').exists())

    def test_subject_teacher_is_given_their_subjects(self):
        self.create(
            self.login(self.admin), role='Subject teacher',
            teaching=[self.maths_link.pk, self.english_link.pk],
        )
        self.maths_link.refresh_from_db()
        self.english_link.refresh_from_db()
        self.assertEqual(self.maths_link.teacher.username, 'newstaff')
        self.assertEqual(self.english_link.teacher.username, 'newstaff')

    def test_subject_teacher_needs_at_least_one_subject(self):
        response = self.create(self.login(self.admin), role='Subject teacher')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newstaff').exists())

    def test_class_not_chosen_for_other_roles_is_ignored(self):
        self.create(self.login(self.admin), role='Read-only staff', class_led=self.jss1a.pk)
        self.jss1a.refresh_from_db()
        self.assertIsNone(self.jss1a.class_teacher)

    def test_duplicate_username_is_refused(self):
        User.objects.create_user('newstaff', password=self.pw)
        response = self.create(self.login(self.admin))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='newstaff').count(), 1)

    def test_unknown_role_is_refused(self):
        response = self.create(self.login(self.admin), role='Hacker')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newstaff').exists())

    def test_class_teacher_cannot_create_staff(self):
        teacher = self.make_user('ct_staff', 'Class teacher')
        response = self.create(self.login(teacher))
        self.assertEqual(response.status_code, 403)

    def test_reassigning_a_class_needs_replace_ticked(self):
        old = self.make_user('old_ct', 'Class teacher')
        self.jss1a.class_teacher = old
        self.jss1a.save()
        self.create(self.login(self.admin), role='Class teacher', class_led=self.jss1a.pk)
        self.jss1a.refresh_from_db()
        self.assertEqual(self.jss1a.class_teacher.username, 'old_ct')

    def test_reassigning_a_class_replaces_its_teacher_when_ticked(self):
        old = self.make_user('old_ct', 'Class teacher')
        self.jss1a.class_teacher = old
        self.jss1a.save()
        self.create(
            self.login(self.admin), role='Class teacher',
            class_led=self.jss1a.pk, replace=True,
        )
        self.jss1a.refresh_from_db()
        self.assertEqual(self.jss1a.class_teacher.username, 'newstaff')

    def test_class_reassignment_is_logged(self):
        self.create(self.login(self.admin), role='Class teacher', class_led=self.jss1a.pk)
        entries = AuditLog.objects.filter(
            model_name='core.schoolclass', action='update', object_id=str(self.jss1a.pk),
        )
        self.assertTrue(any('class_teacher_id' in entry.changes for entry in entries))

    def test_teaching_assignment_is_logged(self):
        self.create(
            self.login(self.admin), role='Subject teacher', teaching=[self.maths_link.pk],
        )
        self.assertTrue(AuditLog.objects.filter(
            model_name='core.classsubject', action='update', object_id=str(self.maths_link.pk),
        ).exists())


class TemporaryPasswordTests(StaffSetup):
    def test_new_account_signs_in_with_the_shown_password(self):
        client = self.login(self.admin)
        self.create(client, role='Read-only staff')
        password = client.session['new_staff']['password']
        self.assertTrue(Client().login(username='newstaff', password=password))

    def test_password_is_shown_once(self):
        client = self.login(self.admin)
        self.create(client, role='Read-only staff')
        first = client.get(reverse('school_admin:staff_created'))
        self.assertEqual(first.status_code, 200)
        self.assertContains(first, first.context['new']['password'])
        second = client.get(reverse('school_admin:staff_created'))
        self.assertEqual(second.status_code, 302)

    def test_password_is_not_written_to_the_audit_log(self):
        client = self.login(self.admin)
        self.create(client, role='Read-only staff')
        password = client.session['new_staff']['password']

        entries = AuditLog.objects.filter(model_name='auth.user', action='create')
        self.assertTrue(entries.filter(object_repr='newstaff').exists())
        for entry in entries:
            self.assertNotIn(password, str(entry.changes))
            self.assertNotIn(password, entry.object_repr)


class StaffListTests(StaffSetup):
    def test_new_staff_appear_in_the_list(self):
        client = self.login(self.admin)
        self.create(client, role='Class teacher', class_led=self.jss1a.pk)
        response = client.get(reverse('school_admin:staff_list'))
        self.assertContains(response, 'newstaff')
        self.assertContains(response, 'JSS1A')


class AssignmentConflictTests(StaffSetup):
    def test_taken_subject_is_refused_without_replace(self):
        other = self.make_user('other_teacher', 'Subject teacher')
        self.maths_link.teacher = other
        self.maths_link.save()
        response = self.create(
            self.login(self.admin), role='Subject teacher', teaching=[self.maths_link.pk],
        )
        self.assertEqual(response.status_code, 200)
        self.maths_link.refresh_from_db()
        self.assertEqual(self.maths_link.teacher, other)

    def test_taken_subject_moves_when_replace_is_ticked(self):
        other = self.make_user('other_teacher', 'Subject teacher')
        self.maths_link.teacher = other
        self.maths_link.save()
        self.create(
            self.login(self.admin), role='Subject teacher',
            teaching=[self.maths_link.pk], replace=True,
        )
        self.maths_link.refresh_from_db()
        self.assertEqual(self.maths_link.teacher.username, 'newstaff')

    def test_class_teacher_can_also_teach_subjects(self):
        self.create(
            self.login(self.admin), role='Class teacher',
            class_led=self.jss1a.pk, teaching=[self.english_link.pk],
        )
        self.jss1a.refresh_from_db()
        self.english_link.refresh_from_db()
        self.assertEqual(self.jss1a.class_teacher.username, 'newstaff')
        self.assertEqual(self.english_link.teacher.username, 'newstaff')