import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.demo import seed_demo, wipe_demo
from core.locking import set_lock
from core.models import Assessment, AuditLog, ClassSubject, SchoolClass, Score, Student, Subject, Term
from core.permissions import can
from core.scoring import save_score
from report_cards.approval import approval_problems, approve_card
from report_cards.comments import save_class_comment, save_head_remark
from report_cards.models import CardPrint, ReportCard, ReportComment
from report_cards.printing import record_print


class Stage4Setup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.english = Subject.objects.create(name='English', code='ENG')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.maths_link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.maths)
        self.english_link = ClassSubject.objects.create(school_class=self.jss1a, subject=self.english)
        self.maths_exam = Assessment.objects.create(
            subject=self.maths, term=self.term, name='Exam', weight=100, max_mark=100,
        )
        self.english_exam = Assessment.objects.create(
            subject=self.english, term=self.term, name='Exam', weight=100, max_mark=100,
        )

        self.ct = self.make_user('ct_s4', 'Class teacher')
        self.head = self.make_user('head_s4', 'Head teacher')
        self.exams = self.make_user('exams_s4', 'Exams officer')
        self.bursar = self.make_user('bursar_s4', 'Bursar')
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password='pass12345!')
        user.groups.add(Group.objects.get(name=role))
        return user

    def enter_scores(self):
        save_score(self.ada, self.maths_exam, Decimal('70'), self.ct)
        save_score(self.ada, self.english_exam, Decimal('55'), self.ct)

    def lock_all(self):
        set_lock(self.maths_link, self.term, True, self.head)
        set_lock(self.english_link, self.term, True, self.head)


class CardLifecycleTests(Stage4Setup):
    def test_card_goes_from_results_to_print_and_back(self):
        self.enter_scores()
        self.assertTrue(any('not locked' in p for p in approval_problems(self.ada, self.term)))
        with self.assertRaises(ValidationError):
            approve_card(self.ada, self.term, self.head)

        self.lock_all()
        save_class_comment(self.ada, self.term, 'Steady progress.', self.ct)
        save_head_remark(self.ada, self.term, 'Promoted.', self.head)
        card = approve_card(self.ada, self.term, self.head)
        self.assertEqual(card.status, 'approved')
        self.assertEqual(card.snapshot['class_teacher_comment'], 'Steady progress.')

        record_print(card, self.exams)
        record_print(card, self.head)
        self.assertEqual(CardPrint.objects.filter(card=card).count(), 2)

        # Frozen: comments and marks refuse changes
        with self.assertRaises(ValidationError):
            save_class_comment(self.ada, self.term, 'Changed', self.ct)
        with self.assertRaises(ValidationError):
            save_score(self.ada, self.english_exam, Decimal('10'), self.ct)

        # Reopen, correct one mark, approve again
        card.reopen('Corrected English mark')
        set_lock(self.english_link, self.term, False, self.head, reason='Corrected English mark')
        save_score(self.ada, self.english_exam, Decimal('80'), self.ct)
        set_lock(self.english_link, self.term, True, self.head)
        save_class_comment(self.ada, self.term, 'Improved in English.', self.ct)
        card = approve_card(self.ada, self.term, self.head)

        english = next(s for s in card.snapshot['subjects'] if s['subject'] == 'English')
        self.assertEqual(english['total'], '80.00')
        self.assertEqual(card.snapshot['class_teacher_comment'], 'Improved in English.')
        self.assertEqual(CardPrint.objects.filter(card=card).count(), 2)

    def test_status_history_is_in_the_audit_log(self):
        self.enter_scores()
        self.lock_all()
        card = approve_card(self.ada, self.term, self.head)
        card.reopen('Correction')
        card = approve_card(self.ada, self.term, self.head)

        statuses = [
            entry.changes['status']
            for entry in AuditLog.objects.filter(
                model_name='report_cards.reportcard', object_id=str(card.pk), action='update',
            ).order_by('pk')
            if 'status' in entry.changes
        ]
        self.assertEqual(statuses, [
            ['draft', 'approved'], ['approved', 'draft'], ['draft', 'approved'],
        ])


class CardRoleTests(Stage4Setup):
    def test_report_card_access_matches_the_role_map(self):
        expected = {
            'view_grades': {'Head teacher', 'Class teacher', 'Subject teacher', 'Exams officer', 'Read-only staff'},
            'approve_report_cards': {'Head teacher'},
            'print_report_cards': {'Head teacher', 'Exams officer'},
            'write_class_comment': {'Class teacher'},
            'write_head_remark': {'Head teacher'},
        }
        roles = [
            'Head teacher', 'Bursar', 'Class teacher', 'Subject teacher',
            'Exams officer', 'Records officer', 'Read-only staff',
        ]
        users = {role: self.make_user('m_' + role.lower().replace(' ', '_'), role) for role in roles}

        for capability, allowed_roles in expected.items():
            for role in roles:
                granted = can(users[role], capability)
                self.assertEqual(granted, role in allowed_roles, f'{role} / {capability}')


class DemoWipeWithReportsTests(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        state = Path(tempfile.mkdtemp()) / 'demo_state.json'
        patcher = patch('core.demo.STATE_FILE', state)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_wipe_removes_demo_report_cards_without_errors(self):
        seed_demo(students_per_class=2)
        term = Term.objects.get(is_demo=True)
        student = Student.objects.filter(is_demo=True).first()
        card = ReportCard.objects.create(student=student, term=term)
        ReportComment.objects.create(student=student, term=term, kind='class_teacher', text='Demo')
        CardPrint.objects.create(card=card, copy_number=1, layout='default')

        wipe_demo()  # would raise ProtectedError without the report wipe

        self.assertFalse(ReportCard.objects.filter(student__is_demo=True).exists())
        self.assertFalse(ReportComment.objects.filter(student__is_demo=True).exists())
        self.assertFalse(CardPrint.objects.exists())
        self.assertFalse(Student.objects.filter(is_demo=True).exists())