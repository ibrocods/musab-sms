from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from core.models import AccountSecurity, AuditLog, ClassSubject, SchoolClass, Subject
from school_admin.accounts import (
    deactivate_staff, reactivate_staff, reset_password, update_details,
)


class AccountSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        self.admin = self.make_user('admin_acc', 'School administrator')
        self.admin2 = self.make_user('admin2_acc', 'School administrator')
        self.teacher = self.make_user('teacher_acc', 'Class teacher')
        self.head = self.make_user('head_acc', 'Head teacher')

        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.jss1a = SchoolClass.objects.create(name='JSS1A', class_teacher=self.teacher)
        self.maths_link = ClassSubject.objects.create(
            school_class=self.jss1a, subject=self.maths, teacher=self.teacher,
        )

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client


class DeactivateTests(AccountSetup):
    def test_deactivation_releases_class_and_subject(self):
        deactivate_staff(actor=self.admin, target=self.teacher)
        self.teacher.refresh_from_db()
        self.jss1a.refresh_from_db()
        self.maths_link.refresh_from_db()
        self.assertFalse(self.teacher.is_active)
        self.assertIsNone(self.jss1a.class_teacher)
        self.assertIsNone(self.maths_link.teacher)

    def test_deactivated_user_cannot_sign_in(self):
        deactivate_staff(actor=self.admin, target=self.teacher)
        self.assertFalse(Client().login(username='teacher_acc', password=self.pw))

    def test_cannot_deactivate_yourself(self):
        with self.assertRaises(ValidationError):
            deactivate_staff(actor=self.admin, target=self.admin)

    def test_cannot_deactivate_the_last_administrator(self):
        deactivate_staff(actor=self.admin, target=self.admin2)
        with self.assertRaises(ValidationError):
            deactivate_staff(actor=self.admin, target=self.admin)

    def test_head_teacher_cannot_deactivate(self):
        with self.assertRaises(PermissionDenied):
            deactivate_staff(actor=self.head, target=self.teacher)

    def test_deactivation_is_logged(self):
        deactivate_staff(actor=self.admin, target=self.teacher)
        entry = AuditLog.objects.filter(
            model_name='auth.user', object_id=str(self.teacher.pk), action='update',
        ).latest('pk')
        self.assertEqual(entry.changes['is_active'], [True, False])


class ReactivateTests(AccountSetup):
    def test_reactivated_user_can_sign_in_but_has_no_assignments(self):
        deactivate_staff(actor=self.admin, target=self.teacher)
        reactivate_staff(actor=self.admin, target=self.teacher)
        self.teacher.refresh_from_db()
        self.jss1a.refresh_from_db()
        self.assertTrue(self.teacher.is_active)
        self.assertIsNone(self.jss1a.class_teacher)
        self.assertTrue(Client().login(username='teacher_acc', password=self.pw))

    def test_reactivating_an_active_user_is_refused(self):
        with self.assertRaises(ValidationError):
            reactivate_staff(actor=self.admin, target=self.teacher)


class ResetPasswordTests(AccountSetup):
    def test_reset_password_signs_in_once_then_forces_change(self):
        password = reset_password(actor=self.admin, target=self.teacher)
        self.assertTrue(Client().login(username='teacher_acc', password=password))
        self.assertTrue(AccountSecurity.objects.get(user=self.teacher).must_change_password)

    def test_pending_user_is_sent_to_change_password_on_every_page(self):
        password = reset_password(actor=self.admin, target=self.teacher)
        client = Client()
        client.login(username='teacher_acc', password=password)
        response = client.get(reverse('home'))
        self.assertRedirects(response, reverse('school_admin:change_password'), fetch_redirect_response=False)

    def test_changing_password_clears_the_flag(self):
        password = reset_password(actor=self.admin, target=self.teacher)
        client = Client()
        client.login(username='teacher_acc', password=password)
        response = client.post(reverse('school_admin:change_password'), {
            'old_password': password,
            'new_password1': 'BrandNew!Pass42',
            'new_password2': 'BrandNew!Pass42',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AccountSecurity.objects.get(user=self.teacher).must_change_password)
        self.assertEqual(client.get(reverse('home')).status_code, 200)

    def test_password_is_not_written_to_the_audit_log(self):
        password = reset_password(actor=self.admin, target=self.teacher)
        for entry in AuditLog.objects.filter(model_name='auth.user', object_id=str(self.teacher.pk)):
            self.assertNotIn(password, str(entry.changes))
            self.assertNotIn(password, entry.object_repr)

    def test_admin_cannot_reset_their_own_password_here(self):
        with self.assertRaises(ValidationError):
            reset_password(actor=self.admin, target=self.admin)

    def test_head_teacher_cannot_reset_passwords(self):
        with self.assertRaises(PermissionDenied):
            reset_password(actor=self.head, target=self.teacher)


class EditTests(AccountSetup):
    def test_changing_role_releases_old_assignments(self):
        update_details(
            actor=self.admin, target=self.teacher,
            first_name='T', last_name='Teacher', email='', role='Read-only staff',
            class_led=None, teaching=[],
        )
        self.jss1a.refresh_from_db()
        self.assertIsNone(self.jss1a.class_teacher)
        self.assertTrue(self.teacher.groups.filter(name='Read-only staff').exists())
        self.assertFalse(self.teacher.groups.filter(name='Class teacher').exists())

    def test_edit_is_logged_with_before_and_after(self):
        update_details(
            actor=self.admin, target=self.teacher,
            first_name='Renamed', last_name='Teacher', email='', role='Class teacher',
            class_led=self.jss1a, teaching=[],
        )
        entry = AuditLog.objects.filter(
            model_name='auth.user', object_id=str(self.teacher.pk), action='update',
        ).latest('pk')
        self.assertEqual(entry.changes['first_name'], ['', 'Renamed'])

    def test_last_administrator_cannot_remove_their_own_role(self):
        self.admin2.is_active = False
        self.admin2.save()
        with self.assertRaises(ValidationError):
            update_details(
                actor=self.admin, target=self.admin,
                first_name='A', last_name='B', email='', role='Head teacher',
                class_led=None, teaching=[],
            )

    def test_edit_page_loads_for_administrator(self):
        url = reverse('school_admin:staff_edit', args=[self.teacher.pk])
        self.assertEqual(self.login(self.admin).get(url).status_code, 200)

    def test_head_teacher_cannot_open_the_edit_page(self):
        url = reverse('school_admin:staff_edit', args=[self.teacher.pk])
        self.assertEqual(self.login(self.head).get(url).status_code, 403)