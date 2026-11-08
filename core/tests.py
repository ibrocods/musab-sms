from django.test import TestCase

# Create your tests here.
from django.core.exceptions import ValidationError
from django.test import Client, TestCase

from .models import SchoolProfile
from .utils import format_student_id
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser, Group
from django.core.management import call_command
from django.utils import timezone

from .models import TemporaryGrant
from .permissions import can

class SchoolProfileTests(TestCase):
    def test_get_returns_the_same_single_profile(self):
        first = SchoolProfile.get()
        second = SchoolProfile.get()
        self.assertEqual(first.pk, 1)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SchoolProfile.objects.count(), 1)

    def test_saving_a_second_profile_overwrites_the_first(self):
        SchoolProfile.objects.create(name='First')
        SchoolProfile(name='Second').save()
        self.assertEqual(SchoolProfile.objects.count(), 1)
        self.assertEqual(SchoolProfile.objects.get().name, 'Second')

    def test_invalid_colour_is_rejected(self):
        profile = SchoolProfile(name='Test', primary_colour='red')
        with self.assertRaises(ValidationError):
            profile.full_clean()


class StudentIdTests(TestCase):
    def test_default_pattern(self):
        self.assertEqual(format_student_id('{year}/{seq:04d}', 2026, 1), '2026/0001')

    def test_custom_pattern(self):
        self.assertEqual(format_student_id('SCH-{seq:05d}', 2026, 42), 'SCH-00042')


class StylesheetTests(TestCase):
    def test_stylesheet_uses_saved_colours(self):
        profile = SchoolProfile.get()
        profile.primary_colour = '#8B0000'
        profile.save()

        response = Client().get('/school.css')

        self.assertEqual(response.status_code, 200)
        self.assertIn('--school-primary: #8B0000', response.content.decode())

from django.contrib.auth.models import Group


class RoleTests(TestCase):
    def test_all_staff_roles_exist(self):
        expected = {
            'Head teacher', 'Bursar', 'Class teacher', 'Subject teacher',
            'Exams officer', 'Records officer', 'Read-only staff',
        }
        self.assertTrue(expected.issubset(set(Group.objects.values_list('name', flat=True))))
from django.contrib.auth.models import User


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass12345!')

    def test_home_redirects_when_logged_out(self):
        response = Client().get('/')
        self.assertEqual(response.status_code, 302)

    def test_home_loads_when_logged_in(self):
        client = Client()
        client.login(username='tester', password='pass12345!')
        response = client.get('/')
        self.assertEqual(response.status_code, 200)

class PermissionTests(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.teacher = User.objects.create_user('teacher1', password='pass12345!')
        self.teacher.groups.add(Group.objects.get(name='Class teacher'))
        self.bursar = User.objects.create_user('bursar1', password='pass12345!')
        self.bursar.groups.add(Group.objects.get(name='Bursar'))

    def test_role_gives_its_capabilities(self):
        self.assertTrue(can(self.teacher, 'mark_attendance'))
        self.assertFalse(can(self.teacher, 'collect_fees'))

    def test_bursar_collects_fees_but_not_grades(self):
        self.assertTrue(can(self.bursar, 'collect_fees'))
        self.assertFalse(can(self.bursar, 'enter_grades'))

    def test_temporary_grant_works_while_active(self):
        TemporaryGrant.objects.create(
            user=self.teacher, capability='collect_fees', reason='Bursar on leave',
            ends_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(can(self.teacher, 'collect_fees'))

    def test_expired_grant_does_not_work(self):
        now = timezone.now()
        TemporaryGrant.objects.create(
            user=self.teacher, capability='collect_fees', reason='Expired',
            starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1),
        )
        self.assertFalse(can(self.teacher, 'collect_fees'))

    def test_revoked_grant_does_not_work(self):
        now = timezone.now()
        TemporaryGrant.objects.create(
            user=self.teacher, capability='collect_fees', reason='Revoked',
            ends_at=now + timedelta(days=1), revoked_at=now,
        )
        self.assertFalse(can(self.teacher, 'collect_fees'))

    def test_anonymous_user_has_nothing(self):
        self.assertFalse(can(AnonymousUser(), 'view_students'))