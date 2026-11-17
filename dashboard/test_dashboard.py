from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import AttendanceRecord, ClassSubject, SchoolClass, SchoolProfile, Student, Subject, Term
from dashboard.services import build_dashboard
from fees.models import FeeItem


class DashboardSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        today = timezone.localdate()
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=today - timedelta(days=30), end_date=today + timedelta(days=30), is_current=True,
        )
        # Every day is a school day, so the tests don't depend on the weekday they run on
        profile = SchoolProfile.get()
        profile.school_days = '0,1,2,3,4,5,6'
        profile.save()

        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.maths_link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.maths)
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

        self.head = self.make_user('head_dash', 'Head teacher')
        self.ct = self.make_user('ct_dash', 'Class teacher')
        self.bursar = self.make_user('bursar_dash', 'Bursar')
        self.readonly = self.make_user('ro_dash', 'Read-only staff')
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def titles(self, user):
        return [item['title'] for item in build_dashboard(user, self.term)['attention']]

    def labels(self, user):
        return [tile['label'] for tile in build_dashboard(user, self.term)['quick']]

    def stat_labels(self, user):
        return [stat['label'] for stat in build_dashboard(user, self.term)['stats']]


class HeadDashboardTests(DashboardSetup):
    def test_head_sees_unlocked_subjects(self):
        self.assertIn('Mathematics: JSS1A', self.titles(self.head))

    def test_head_sees_approve_tile(self):
        self.assertIn('Approve cards', self.labels(self.head))

    def test_head_sees_fee_stats_because_they_can_view_fees(self):
        self.assertIn('Outstanding', self.stat_labels(self.head))

    def test_head_has_no_fee_setup_tile(self):
        self.assertNotIn('Fee setup', self.labels(self.head))

class ClassTeacherDashboardTests(DashboardSetup):
    def test_unmarked_register_is_flagged(self):
        self.assertTrue(any('Register not marked' in t for t in self.titles(self.ct)))

    def test_marking_the_register_clears_the_flag(self):
        AttendanceRecord.objects.create(
            student=self.ada, school_class=self.jss1a, term=self.term,
            date=timezone.localdate(), status='P',
        )
        self.assertFalse(any('Register not marked' in t for t in self.titles(self.ct)))

    def test_class_teacher_sees_no_outstanding_fees(self):
        self.assertNotIn('Outstanding', self.stat_labels(self.ct))


class BursarDashboardTests(DashboardSetup):
    def test_outstanding_fees_are_shown(self):
        FeeItem.objects.create(name='Tuition', amount=Decimal('50000'), term=self.term)
        self.assertIn('Outstanding', self.stat_labels(self.bursar))
        self.assertTrue(build_dashboard(self.bursar, self.term)['debtors'])

    def test_bursar_sees_record_payment_tile(self):
        self.assertIn('Record payment', self.labels(self.bursar))


class ReadOnlyDashboardTests(DashboardSetup):
    def test_read_only_has_no_write_actions(self):
        labels = self.labels(self.readonly)
        for forbidden in ['Add student', 'Mark register', 'Scores', 'Record payment', 'Approve cards']:
            self.assertNotIn(forbidden, labels)


class NoTermTests(DashboardSetup):
    def test_missing_term_shows_a_warning(self):
        data = build_dashboard(self.head, None)
        self.assertEqual(data['attention'][0]['title'], 'No current term')


class HomePageTests(DashboardSetup):
    def test_home_loads_for_every_role(self):
        for user in [self.head, self.ct, self.bursar, self.readonly]:
            client = Client()
            client.login(username=user.username, password=self.pw)
            response = client.get(reverse('home'))
            self.assertEqual(response.status_code, 200, user.username)

    def test_home_redirects_when_signed_out(self):
        response = Client().get(reverse('home'))
        self.assertEqual(response.status_code, 302)