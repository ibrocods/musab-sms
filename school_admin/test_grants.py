from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog, TemporaryGrant
from core.permissions import can
from school_admin.grants import MAX_GRANT_DAYS, grant_temporary, revoke_grant


class GrantSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        self.admin = self.make_user('admin_grant', 'School administrator')
        self.head = self.make_user('head_grant', 'Head teacher')
        self.staff = self.make_user('staff_grant', 'Class teacher')
        self.tomorrow = timezone.localdate() + timedelta(days=1)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client

    def give(self, actor=None, **overrides):
        data = {
            'actor': actor or self.admin,
            'target': self.staff,
            'capability': 'collect_fees',
            'reason': 'Bursar on leave',
            'ends_on': self.tomorrow,
        }
        data.update(overrides)
        return grant_temporary(**data)


class GrantRuleTests(GrantSetup):
    def test_grant_gives_access_while_active(self):
        self.assertFalse(can(self.staff, 'collect_fees'))
        self.give()
        self.assertTrue(can(self.staff, 'collect_fees'))

    def test_access_stops_when_the_end_passes(self):
        grant = self.give()
        TemporaryGrant.objects.filter(pk=grant.pk).update(
            ends_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertFalse(can(self.staff, 'collect_fees'))

    def test_ending_access_now_takes_effect_immediately(self):
        grant = self.give()
        revoke_grant(actor=self.admin, grant=grant)
        self.assertFalse(can(self.staff, 'collect_fees'))
        self.assertTrue(TemporaryGrant.objects.filter(pk=grant.pk).exists())

    def test_ending_twice_is_refused(self):
        grant = self.give()
        revoke_grant(actor=self.admin, grant=grant)
        with self.assertRaises(ValidationError):
            revoke_grant(actor=self.admin, grant=grant)

    def test_cannot_give_access_to_yourself(self):
        with self.assertRaises(ValidationError):
            self.give(target=self.admin)

    def test_staff_management_cannot_be_given_temporarily(self):
        with self.assertRaises(ValidationError):
            self.give(capability='manage_staff')

    def test_reason_is_required(self):
        with self.assertRaises(ValidationError):
            self.give(reason='   ')

    def test_end_date_in_the_past_is_refused(self):
        with self.assertRaises(ValidationError):
            self.give(ends_on=timezone.localdate() - timedelta(days=1))

    def test_duration_is_limited(self):
        with self.assertRaises(ValidationError):
            self.give(ends_on=timezone.localdate() + timedelta(days=MAX_GRANT_DAYS + 5))

    def test_inactive_staff_cannot_receive_access(self):
        self.staff.is_active = False
        self.staff.save()
        with self.assertRaises(ValidationError):
            self.give()

    def test_head_teacher_cannot_give_access(self):
        with self.assertRaises(PermissionDenied):
            self.give(actor=self.head)

    def test_giving_and_ending_are_logged(self):
        grant = self.give()
        revoke_grant(actor=self.admin, grant=grant)
        self.assertTrue(AuditLog.objects.filter(
            model_name='core.temporarygrant', action='create', object_id=str(grant.pk),
        ).exists())
        self.assertTrue(any(
            'revoked_at' in entry.changes
            for entry in AuditLog.objects.filter(
                model_name='core.temporarygrant', action='update', object_id=str(grant.pk),
            )
        ))


class GrantViewTests(GrantSetup):
    def test_administrator_sees_the_list(self):
        response = self.login(self.admin).get(reverse('school_admin:grant_list'))
        self.assertEqual(response.status_code, 200)

    def test_head_teacher_cannot_open_the_list(self):
        response = self.login(self.head).get(reverse('school_admin:grant_list'))
        self.assertEqual(response.status_code, 403)

    def test_administrator_gives_access_through_the_form(self):
        response = self.login(self.admin).post(reverse('school_admin:grant_create'), {
            'user': self.staff.pk,
            'capability': 'collect_fees',
            'reason': 'Covering the bursar',
            'ends_on': self.tomorrow.isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(can(self.staff, 'collect_fees'))

    def test_administrator_ends_access_from_the_list(self):
        grant = self.give()
        response = self.login(self.admin).post(reverse('school_admin:grant_revoke', args=[grant.pk]))
        self.assertEqual(response.status_code, 302)
        grant.refresh_from_db()
        self.assertIsNotNone(grant.revoked_at)