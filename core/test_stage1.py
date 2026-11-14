from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AuditLog, SchoolClass, SchoolProfile, Student, TemporaryGrant
from .scope import visible_students


class Stage1Setup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.password = 'pass12345!'

        self.teacher = User.objects.create_user('ct', password=self.password)
        self.teacher.groups.add(Group.objects.get(name='Class teacher'))
        self.head = User.objects.create_user('hd', password=self.password)
        self.head.groups.add(Group.objects.get(name='Head teacher'))
        self.records = User.objects.create_user('rec', password=self.password)
        self.records.groups.add(Group.objects.get(name='Records officer'))

        self.class_a = SchoolClass.objects.create(name='JSS1A', class_teacher=self.teacher)
        self.class_b = SchoolClass.objects.create(name='JSS2B')

        self.s1 = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.class_a)
        self.s2 = Student.objects.create(first_name='Musa', last_name='Ali', school_class=self.class_b)

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.password)
        return client


class StudentIdTests(Stage1Setup):
    def test_ids_follow_the_pattern(self):
        year = timezone.now().year
        self.assertEqual(self.s1.student_id, f'{year}/0001')
        self.assertEqual(self.s2.student_id, f'{year}/0002')

    def test_archived_student_id_is_not_reused(self):
        self.s1.is_archived = True
        self.s1.save()
        new = Student.objects.create(first_name='New', last_name='One')
        self.assertTrue(new.student_id.endswith('/0003'))

    def test_custom_pattern_is_used(self):
        profile = SchoolProfile.get()
        profile.student_id_pattern = 'SCH-{seq:05d}'
        profile.save()
        new = Student.objects.create(first_name='New', last_name='One')
        self.assertEqual(new.student_id, 'SCH-00003')

    def test_pattern_without_sequence_is_refused(self):
        profile = SchoolProfile.get()
        profile.student_id_pattern = '{year}'
        profile.save()
        with self.assertRaises(ValueError):
            Student.objects.create(first_name='New', last_name='One')


class StudentVisibilityTests(Stage1Setup):
    def test_class_teacher_sees_only_their_class(self):
        self.assertEqual(list(visible_students(self.teacher)), [self.s1])

    def test_head_teacher_sees_all_students(self):
        self.assertEqual(visible_students(self.head).count(), 2)

    def test_anonymous_user_sees_no_students(self):
        self.assertEqual(visible_students(AnonymousUser()).count(), 0)

    def test_archived_students_are_hidden_from_the_list(self):
        self.s1.is_archived = True
        self.s1.save()
        response = self.login(self.head).get(reverse('student_list'))
        self.assertNotIn(self.s1, response.context['students'])
        self.assertIn(self.s2, response.context['students'])

    def test_archiving_keeps_the_record(self):
        self.login(self.records).post(reverse('student_archive', args=[self.s1.pk]))
        self.s1.refresh_from_db()
        self.assertTrue(self.s1.is_archived)
        self.assertIsNotNone(self.s1.archived_at)


class StudentPermissionViewTests(Stage1Setup):
    def test_anonymous_user_is_sent_to_login(self):
        response = Client().get(reverse('student_list'))
        self.assertEqual(response.status_code, 302)

    def test_class_teacher_cannot_add_students(self):
        response = self.login(self.teacher).get(reverse('student_create'))
        self.assertEqual(response.status_code, 403)

    def test_class_teacher_cannot_archive_students(self):
        response = self.login(self.teacher).post(reverse('student_archive', args=[self.s1.pk]))
        self.assertEqual(response.status_code, 403)
        self.s1.refresh_from_db()
        self.assertFalse(self.s1.is_archived)

    def test_records_officer_can_add_a_student(self):
        response = self.login(self.records).post(reverse('student_create'), {
            'first_name': 'New', 'last_name': 'Student', 'admission_year': 2026,
            'school_class': self.class_b.pk, 'gender': '', 'parent_name': '',
            'parent_phone': '', 'parent_email': '', 'address': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(last_name='Student').exists())


class AuditLogTests(Stage1Setup):
    def test_creating_a_student_is_logged_with_the_actor(self):
        self.login(self.records).post(reverse('student_create'), {
            'first_name': 'Logged', 'last_name': 'Student', 'admission_year': 2026,
            'gender': '', 'parent_name': '', 'parent_phone': '', 'parent_email': '', 'address': '',
        })
        self.assertTrue(AuditLog.objects.filter(
            model_name='core.student', action='create', username='rec',
        ).exists())

    def test_archiving_is_logged_as_a_change(self):
        self.login(self.records).post(reverse('student_archive', args=[self.s1.pk]))
        entries = AuditLog.objects.filter(model_name='core.student', action='update', object_id=str(self.s1.pk))
        self.assertTrue(any('is_archived' in entry.changes for entry in entries))

    def test_sign_in_is_logged(self):
        self.login(self.head)
        self.assertTrue(AuditLog.objects.filter(action='login', username='hd').exists())

    def test_revoking_a_grant_is_logged(self):
        grant = TemporaryGrant.objects.create(
            user=self.teacher, capability='collect_fees', reason='Test',
            ends_at=timezone.now() + timezone.timedelta(days=1),
        )
        grant.revoked_at = timezone.now()
        grant.save()
        entries = AuditLog.objects.filter(model_name='core.temporarygrant', action='update', object_id=str(grant.pk))
        self.assertTrue(any('revoked_at' in entry.changes for entry in entries))

    def test_changes_made_outside_a_request_have_no_user(self):
        entry = AuditLog.objects.filter(model_name='core.student', action='create', object_id=str(self.s1.pk)).first()
        self.assertEqual(entry.username, '')

    def test_audit_entries_cannot_be_edited_or_deleted(self):
        entry = AuditLog.objects.first()
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            entry.delete()

class PatternSafetyTests(TestCase):
    def test_profile_refuses_a_pattern_without_sequence(self):
        profile = SchoolProfile.get()
        profile.student_id_pattern = '{year}'
        with self.assertRaises(ValidationError):
            profile.save()