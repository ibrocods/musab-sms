from datetime import date

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from .attendance import non_school_reason, save_register
from .models import AttendanceRecord, AuditLog, NonSchoolDay, SchoolClass, SchoolProfile, Student, Term


class AttendanceRulesSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.ct = User.objects.create_user('ct_rules', password='pass12345!')
        self.ct.groups.add(Group.objects.get(name='Class teacher'))
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.bola = Student.objects.create(first_name='Bola', last_name='Ade', school_class=self.jss1a)
        self.monday = date(2026, 10, 5)     # Monday
        self.saturday = date(2026, 10, 10)  # Saturday


class SchoolDayTests(AttendanceRulesSetup):
    def test_weekday_is_a_school_day(self):
        self.assertIsNone(non_school_reason(self.monday))

    def test_weekend_is_refused(self):
        with self.assertRaises(ValidationError):
            save_register(self.jss1a, self.term, self.saturday, {self.ada: 'P'}, self.ct)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_public_holiday_is_refused_with_its_name(self):
        NonSchoolDay.objects.create(date=self.monday, description='Test holiday')
        with self.assertRaises(ValidationError) as context:
            save_register(self.jss1a, self.term, self.monday, {self.ada: 'P'}, self.ct)
        self.assertIn('Test holiday', str(context.exception))
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_school_days_setting_can_open_saturdays(self):
        profile = SchoolProfile.get()
        profile.school_days = '0,1,2,3,4,5'
        profile.save()
        save_register(self.jss1a, self.term, self.saturday, {self.ada: 'P'}, self.ct)
        self.assertTrue(AttendanceRecord.objects.filter(date=self.saturday).exists())


class ExcusedNoteTests(AttendanceRulesSetup):
    def test_excused_without_a_note_is_refused(self):
        with self.assertRaises(ValidationError):
            save_register(self.jss1a, self.term, self.monday, {self.ada: 'E'}, self.ct)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_excused_with_a_note_is_saved(self):
        save_register(
            self.jss1a, self.term, self.monday, {self.ada: 'E'}, self.ct,
            notes={self.ada: 'Sick, letter received'},
        )
        record = AttendanceRecord.objects.get(student=self.ada, date=self.monday)
        self.assertEqual(record.note, 'Sick, letter received')


class AuditVolumeTests(AttendanceRulesSetup):
    def test_one_audit_entry_per_register_save(self):
        save_register(self.jss1a, self.term, self.monday, {self.ada: 'P', self.bola: 'A'}, self.ct)
        self.assertEqual(AuditLog.objects.filter(model_name='core.attendancerecord').count(), 1)

    def test_audit_entry_lists_only_what_changed(self):
        save_register(self.jss1a, self.term, self.monday, {self.ada: 'P', self.bola: 'A'}, self.ct)
        save_register(self.jss1a, self.term, self.monday, {self.ada: 'P', self.bola: 'L'}, self.ct)
        entry = AuditLog.objects.filter(model_name='core.attendancerecord').order_by('pk').last()
        self.assertIn(self.bola.student_id, entry.changes)
        self.assertNotIn(self.ada.student_id, entry.changes)

    def test_saving_an_unchanged_register_writes_no_new_entry(self):
        save_register(self.jss1a, self.term, self.monday, {self.ada: 'P'}, self.ct)
        save_register(self.jss1a, self.term, self.monday, {self.ada: 'P'}, self.ct)
        self.assertEqual(AuditLog.objects.filter(model_name='core.attendancerecord').count(), 1)