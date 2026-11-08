from django.test import TestCase

# Create your tests here.
from django.core.exceptions import ValidationError
from django.test import Client, TestCase

from .models import SchoolProfile
from .utils import format_student_id


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