from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase

from core.permissions import can


class AdministrationRoleTests(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.admin = self.make_user('schooladmin', 'School administrator')
        self.head = self.make_user('head_adm', 'Head teacher')
        self.teacher = self.make_user('ct_adm', 'Class teacher')

    def make_user(self, username, role):
        user = User.objects.create_user(username, password='pass12345!')
        user.groups.add(Group.objects.get(name=role))
        return user

    def test_school_administrator_manages_staff_and_setup(self):
        self.assertTrue(can(self.admin, 'manage_staff'))
        self.assertTrue(can(self.admin, 'manage_school_setup'))
        self.assertTrue(can(self.admin, 'view_audit_log'))

    def test_school_administrator_has_no_money_rights(self):
        self.assertFalse(can(self.admin, 'collect_fees'))
        self.assertFalse(can(self.admin, 'reverse_payments'))

    def test_head_teacher_cannot_manage_staff(self):
        self.assertFalse(can(self.head, 'manage_staff'))
        self.assertFalse(can(self.head, 'manage_school_setup'))

    def test_class_teacher_cannot_view_the_audit_log(self):
        self.assertFalse(can(self.teacher, 'view_audit_log'))