from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.locking import set_lock
from core.models import (
    Assessment, AuditLog, ClassSubject, SchoolClass, Score, Student, Subject, Term,
)
from report_cards.approval import approval_problems, approve_card, build_snapshot
from report_cards.comments import save_class_comment, save_head_remark
from report_cards.models import ReportCard


class ApprovalSetup(TestCase):
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
        for subject in (self.maths, self.english):
            Assessment.objects.create(subject=subject, term=self.term, name='Test', weight=30, max_mark=100)
            Assessment.objects.create(subject=subject, term=self.term, name='Exam', weight=70, max_mark=100)

        self.ct = self.make_user('ct_appr', 'Class teacher')
        self.head = self.make_user('head_appr', 'Head teacher')
        self.bursar = self.make_user('bursar_appr', 'Bursar')
        self.jss1a.class_teacher = self.ct
        self.jss1a.save()

        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password='pass12345!')
        user.groups.add(Group.objects.get(name=role))
        return user

    def enter_all(self, student):
        for subject in (self.maths, self.english):
            for assessment in Assessment.objects.filter(subject=subject, term=self.term):
                Score.objects.create(student=student, assessment=assessment, score=Decimal('60'))

    def lock_everything(self):
        for link in (self.maths_link, self.english_link):
            set_lock(link, self.term, True, self.head)

    def ready_student(self):
        self.enter_all(self.ada)
        self.lock_everything()


class ProblemListTests(ApprovalSetup):
    def test_ready_student_has_no_problems(self):
        self.ready_student()
        self.assertEqual(approval_problems(self.ada, self.term), [])

    def test_every_problem_is_listed_not_just_the_first(self):
        problems = approval_problems(self.ada, self.term)
        subjects_named = ' '.join(problems)
        self.assertIn('Mathematics', subjects_named)
        self.assertIn('English', subjects_named)
        self.assertGreaterEqual(len(problems), 4)

    def test_incomplete_subject_is_reported(self):
        Score.objects.create(
            student=self.ada,
            assessment=Assessment.objects.get(subject=self.maths, name='Test'),
            score=Decimal('60'),
        )
        self.lock_everything()
        problems = approval_problems(self.ada, self.term)
        self.assertTrue(any('Mathematics: result incomplete' in p for p in problems))

    def test_unlocked_subject_is_reported(self):
        self.enter_all(self.ada)
        set_lock(self.maths_link, self.term, True, self.head)
        problems = approval_problems(self.ada, self.term)
        self.assertTrue(any('English: results are not locked' in p for p in problems))
        self.assertFalse(any('Mathematics' in p for p in problems))

    def test_student_without_a_class_is_reported(self):
        loose = Student.objects.create(first_name='No', last_name='Class')
        self.assertEqual(approval_problems(loose, self.term), ['The student is not in a class.'])


class ApproveTests(ApprovalSetup):
    def test_head_teacher_approves_a_ready_card(self):
        self.ready_student()
        card = approve_card(self.ada, self.term, self.head)
        self.assertEqual(card.status, 'approved')
        self.assertEqual(card.approved_by, self.head)

    def test_approval_refused_with_listed_reasons(self):
        with self.assertRaises(ValidationError) as context:
            approve_card(self.ada, self.term, self.head)
        self.assertGreaterEqual(len(context.exception.messages), 4)
        card = ReportCard.objects.get(student=self.ada, term=self.term)
        self.assertEqual(card.status, 'draft')

    def test_bursar_cannot_approve(self):
        self.ready_student()
        with self.assertRaises(PermissionDenied):
            approve_card(self.ada, self.term, self.bursar)
        self.assertFalse(ReportCard.objects.filter(status='approved').exists())

    def test_class_teacher_cannot_approve(self):
        self.ready_student()
        with self.assertRaises(PermissionDenied):
            approve_card(self.ada, self.term, self.ct)

    def test_approving_twice_is_refused(self):
        self.ready_student()
        approve_card(self.ada, self.term, self.head)
        with self.assertRaises(ValidationError):
            approve_card(self.ada, self.term, self.head)

    def test_approval_is_logged(self):
        self.ready_student()
        card = approve_card(self.ada, self.term, self.head)
        entry = AuditLog.objects.filter(
            model_name='report_cards.reportcard', object_id=str(card.pk), action='update',
        ).latest('pk')
        self.assertEqual(entry.changes['status'], ['draft', 'approved'])


class SnapshotTests(ApprovalSetup):
    def test_snapshot_holds_the_printed_figures(self):
        self.ready_student()
        save_class_comment(self.ada, self.term, 'Steady progress.', self.ct)
        save_head_remark(self.ada, self.term, 'Well done.', self.head)
        card = approve_card(self.ada, self.term, self.head)

        snapshot = card.snapshot
        self.assertEqual(snapshot['student_name'], 'Obi Ada')
        self.assertEqual(len(snapshot['subjects']), 2)
        self.assertEqual(snapshot['class_teacher_comment'], 'Steady progress.')
        self.assertEqual(snapshot['head_teacher_remark'], 'Well done.')

    def test_amounts_are_stored_as_exact_strings(self):
        self.ready_student()
        card = approve_card(self.ada, self.term, self.head)
        self.assertIsInstance(card.snapshot['average'], str)
        self.assertEqual(card.snapshot['average'], '60.00')

    def test_later_score_change_does_not_alter_the_approved_snapshot(self):
        self.ready_student()
        card = approve_card(self.ada, self.term, self.head)
        before = card.snapshot

        # The results are locked, so no teacher can change them. The snapshot must still hold.
        Score.objects.filter(student=self.ada).update(score=Decimal('1'))
        card.refresh_from_db()
        self.assertEqual(card.snapshot, before)

    def test_comment_written_after_approval_does_not_appear(self):
        self.ready_student()
        card = approve_card(self.ada, self.term, self.head)
        self.assertEqual(card.snapshot['class_teacher_comment'], '')
        save_class_comment(self.ada, self.term, 'Too late.', self.ct)
        card.refresh_from_db()
        self.assertEqual(card.snapshot['class_teacher_comment'], '')

    def test_snapshot_is_built_from_current_figures_only(self):
        self.ready_student()
        snapshot = build_snapshot(self.ada, self.term)
        self.assertEqual(snapshot['average'], '60.00')
        self.assertEqual(snapshot['position'], 1)


class ReopenThenApproveTests(ApprovalSetup):
    def test_reopened_card_approves_again_with_fresh_figures(self):
        self.ready_student()
        card = approve_card(self.ada, self.term, self.head)
        card.reopen('Correction')

        # Correct a maths mark: unlock, change, relock
        set_lock(self.maths_link, self.term, False, self.head, reason='Correction')
        Score.objects.filter(student=self.ada, assessment__subject=self.maths).update(score=Decimal('90'))
        set_lock(self.maths_link, self.term, True, self.head)

        card = approve_card(self.ada, self.term, self.head)
        self.assertEqual(card.status, 'approved')

        maths = next(s for s in card.snapshot['subjects'] if s['subject'] == 'Mathematics')
        english = next(s for s in card.snapshot['subjects'] if s['subject'] == 'English')
        self.assertEqual(maths['total'], '90.00')
        self.assertEqual(english['total'], '60.00')