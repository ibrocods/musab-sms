from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from core.locking import set_lock
from core.models import Assessment, ClassSubject, SchoolClass, SchoolProfile, Score, Student, Subject, Term
from report_cards.approval import approve_card
from report_cards.cards import get_or_create_draft
from report_cards.layouts import layout_template_name, render_card


class LayoutSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.maths)
        Assessment.objects.create(subject=self.maths, term=self.term, name='Exam', weight=100, max_mark=100)

        self.ct = self.make_user('ct_lay', 'Class teacher')
        self.head = self.make_user('head_lay', 'Head teacher')
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password='pass12345!')
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password='pass12345!')
        return client

    def approved_card(self):
        Score.objects.create(
            student=self.ada, assessment=Assessment.objects.get(subject=self.maths), score=Decimal('70'),
        )
        set_lock(self.link, self.term, True, self.head)
        return approve_card(self.ada, self.term, self.head)


class LayoutRenderTests(LayoutSetup):
    def test_default_layout_is_used(self):
        self.assertEqual(layout_template_name(), 'report_cards/layouts/default/card.html')

    def test_unknown_layout_falls_back_to_default(self):
        profile = SchoolProfile.get()
        profile.report_card_layout = 'does_not_exist'
        profile.save()
        self.assertEqual(layout_template_name(), 'report_cards/layouts/default/card.html')

    def test_approved_card_renders_the_snapshot_figures(self):
        card = self.approved_card()
        html = render_card(None, card)
        self.assertIn('Mathematics', html)
        self.assertIn('70.00', html)
        self.assertNotIn('DRAFT', html)

    def test_draft_card_is_marked_draft(self):
        card = get_or_create_draft(self.ada, self.term)
        html = render_card(None, card)
        self.assertIn('DRAFT', html)

    def test_card_shows_the_snapshot_not_live_scores(self):
        card = self.approved_card()
        Score.objects.filter(student=self.ada).update(score=Decimal('5'))
        html = render_card(None, card)
        self.assertIn('70.00', html)
        self.assertNotIn('>5.00<', html)


class LayoutPageTests(LayoutSetup):
    def test_head_teacher_can_open_an_approved_card(self):
        self.approved_card()
        url = reverse('report_cards:card', args=[self.ada.pk])
        response = self.login(self.head).get(url, {'term': self.term.pk})
        self.assertEqual(response.status_code, 200)

    def test_print_is_refused_for_a_draft(self):
        get_or_create_draft(self.ada, self.term)
        url = reverse('report_cards:print', args=[self.ada.pk])
        response = self.login(self.head).get(url, {'term': self.term.pk})
        self.assertEqual(response.status_code, 403)

    def test_print_works_for_an_approved_card(self):
        self.approved_card()
        url = reverse('report_cards:print', args=[self.ada.pk])
        response = self.login(self.head).get(url, {'term': self.term.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Obi Ada', response.content.decode())

    def test_class_teacher_can_comment_only_on_a_draft(self):
        url = reverse('report_cards:card', args=[self.ada.pk])
        self.login(self.ct).get(url, {'term': self.term.pk})
        self.approved_card()
        response = self.login(self.ct).get(url, {'term': self.term.pk})
        self.assertFalse(response.context['can_comment'])

    def test_comment_on_an_approved_card_is_refused(self):
        self.approved_card()
        url = reverse('report_cards:comment', args=[self.ada.pk])
        self.login(self.ct).post(url, {'kind': 'class_teacher', 'text': 'Late note'})
        self.assertEqual(
            self.approved_card_comment(), '',
        )

    def approved_card_comment(self):
        from report_cards.models import ReportComment
        comment = ReportComment.objects.filter(student=self.ada, kind='class_teacher').first()
        return comment.text if comment else ''

    def test_bursar_cannot_open_a_report_card_page(self):
        bursar = self.make_user('bursar_lay', 'Bursar')
        url = reverse('report_cards:card', args=[self.ada.pk])
        response = self.login(bursar).get(url, {'term': self.term.pk})
        self.assertEqual(response.status_code, 403)