from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from core.locking import set_lock
from core.models import Assessment, AuditLog, ClassSubject, SchoolClass, SchoolProfile, Score, Student, Subject, Term
from report_cards.approval import approve_card
from report_cards.cards import get_or_create_draft
from report_cards.layouts import layout_template_name, render_card
from report_cards.models import CardPrint
from report_cards.printing import record_print


class PrintSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.maths)
        Assessment.objects.create(subject=self.maths, term=self.term, name='Exam', weight=100, max_mark=100)

        self.ct = self.make_user('ct_print', 'Class teacher')
        self.head = self.make_user('head_print', 'Head teacher')
        self.exams = self.make_user('exams_print', 'Exams officer')
        self.bursar = self.make_user('bursar_print', 'Bursar')
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client

    def approved_card(self):
        Score.objects.create(
            student=self.ada, assessment=Assessment.objects.get(subject=self.maths), score=Decimal('70'),
        )
        set_lock(self.link, self.term, True, self.head)
        return approve_card(self.ada, self.term, self.head)


class PrintRuleTests(PrintSetup):
    def test_head_teacher_records_a_print(self):
        card = self.approved_card()
        self.assertEqual(record_print(card, self.head), 1)
        self.assertEqual(CardPrint.objects.get().printed_by, self.head)

    def test_copies_are_numbered_in_order(self):
        card = self.approved_card()
        self.assertEqual(record_print(card, self.head), 1)
        self.assertEqual(record_print(card, self.exams), 2)
        self.assertEqual(CardPrint.objects.filter(card=card).count(), 2)

    def test_draft_cannot_be_printed_as_final(self):
        card = get_or_create_draft(self.ada, self.term)
        with self.assertRaises(ValidationError):
            record_print(card, self.head)
        self.assertFalse(CardPrint.objects.exists())

    def test_class_teacher_cannot_print(self):
        card = self.approved_card()
        with self.assertRaises(PermissionDenied):
            record_print(card, self.ct)

    def test_bursar_cannot_print(self):
        card = self.approved_card()
        with self.assertRaises(PermissionDenied):
            record_print(card, self.bursar)

    def test_print_record_cannot_be_changed(self):
        card = self.approved_card()
        record_print(card, self.head)
        printed = CardPrint.objects.get()
        printed.copy_number = 99
        with self.assertRaises(PermissionError):
            printed.save()

    def test_print_record_cannot_be_deleted(self):
        card = self.approved_card()
        record_print(card, self.head)
        with self.assertRaises(PermissionError):
            CardPrint.objects.get().delete()
        self.assertTrue(CardPrint.objects.exists())

    def test_printing_is_logged(self):
        card = self.approved_card()
        record_print(card, self.head)
        self.assertTrue(AuditLog.objects.filter(
            model_name='report_cards.cardprint', action='create',
        ).exists())


class PrintPageTests(PrintSetup):
    def test_print_page_records_one_copy(self):
        self.approved_card()
        url = reverse('report_cards:print', args=[self.ada.pk])
        response = self.login(self.head).get(url, {'term': self.term.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CardPrint.objects.count(), 1)

    def test_draft_preview_records_nothing(self):
        get_or_create_draft(self.ada, self.term)
        url = reverse('report_cards:card', args=[self.ada.pk])
        response = self.login(self.head).get(url, {'term': self.term.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CardPrint.objects.exists())

    def test_class_teacher_cannot_open_the_print_page(self):
        self.approved_card()
        url = reverse('report_cards:print', args=[self.ada.pk])
        response = self.login(self.ct).get(url, {'term': self.term.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CardPrint.objects.exists())


class LayoutSwitchTests(PrintSetup):
    def test_switching_to_compact_layout_changes_the_output(self):
        card = self.approved_card()
        profile = SchoolProfile.get()
        profile.report_card_layout = 'compact'
        profile.save()

        self.assertEqual(layout_template_name(), 'report_cards/layouts/compact/card.html')
        html = render_card(None, card)
        self.assertIn('COMPACT LAYOUT', html)
        self.assertIn('Mathematics', html)

    def test_prints_record_the_layout_used(self):
        card = self.approved_card()
        profile = SchoolProfile.get()
        profile.report_card_layout = 'compact'
        profile.save()
        record_print(card, self.head)
        self.assertEqual(CardPrint.objects.get().layout, 'compact')