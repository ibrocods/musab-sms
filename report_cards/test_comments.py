from datetime import date

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import AuditLog, SchoolClass, SchoolProfile, Student, Term
from report_cards.comments import comments_for, save_class_comment, save_head_remark
from report_cards.models import ReportComment


class CommentSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.ct = self.make_user('ct_comment', 'Class teacher')
        self.other_ct = self.make_user('other_ct', 'Class teacher')
        self.head = self.make_user('head_comment', 'Head teacher')
        self.bursar = self.make_user('bursar_comment', 'Bursar')

        self.jss1a = SchoolClass.objects.create(name='JSS1A', class_teacher=self.ct)
        self.jss2b = SchoolClass.objects.create(name='JSS2B', class_teacher=self.other_ct)
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password='pass12345!')
        user.groups.add(Group.objects.get(name=role))
        return user


class ClassTeacherCommentTests(CommentSetup):
    def test_class_teacher_writes_for_own_class(self):
        comment = save_class_comment(self.ada, self.term, 'Ada is improving.', self.ct)
        self.assertEqual(comment.text, 'Ada is improving.')
        self.assertEqual(comment.written_by, self.ct)

    def test_class_teacher_cannot_write_for_another_class(self):
        stranger = Student.objects.create(first_name='Bola', last_name='Ade', school_class=self.jss2b)
        with self.assertRaises(PermissionDenied):
            save_class_comment(stranger, self.term, 'Not mine.', self.ct)
        self.assertFalse(ReportComment.objects.filter(student=stranger).exists())

    def test_head_teacher_cannot_write_class_comment(self):
        with self.assertRaises(PermissionDenied):
            save_class_comment(self.ada, self.term, 'Trying.', self.head)

    def test_bursar_cannot_write_class_comment(self):
        with self.assertRaises(PermissionDenied):
            save_class_comment(self.ada, self.term, 'Trying.', self.bursar)

    def test_writing_again_replaces_the_text(self):
        save_class_comment(self.ada, self.term, 'First draft.', self.ct)
        save_class_comment(self.ada, self.term, 'Final text.', self.ct)
        self.assertEqual(ReportComment.objects.filter(kind='class_teacher').count(), 1)
        self.assertEqual(comments_for(self.ada, self.term)['class_teacher'].text, 'Final text.')

    def test_blank_spaces_are_trimmed(self):
        comment = save_class_comment(self.ada, self.term, '   Good work.   ', self.ct)
        self.assertEqual(comment.text, 'Good work.')


class HeadRemarkTests(CommentSetup):
    def test_head_teacher_writes_a_remark(self):
        remark = save_head_remark(self.ada, self.term, 'Promoted with distinction.', self.head)
        self.assertEqual(remark.kind, 'head_teacher')

    def test_class_teacher_cannot_write_head_remark(self):
        with self.assertRaises(PermissionDenied):
            save_head_remark(self.ada, self.term, 'Trying.', self.ct)

    def test_head_remark_is_separate_from_class_comment(self):
        save_class_comment(self.ada, self.term, 'Class comment.', self.ct)
        save_head_remark(self.ada, self.term, 'Head remark.', self.head)
        found = comments_for(self.ada, self.term)
        self.assertEqual(found['class_teacher'].text, 'Class comment.')
        self.assertEqual(found['head_teacher'].text, 'Head remark.')


class LengthTests(CommentSetup):
    def test_comment_over_the_limit_is_refused(self):
        profile = SchoolProfile.get()
        profile.comment_max_length = 20
        profile.save()
        with self.assertRaises(ValidationError):
            save_class_comment(self.ada, self.term, 'x' * 21, self.ct)
        self.assertFalse(ReportComment.objects.exists())

    def test_comment_at_the_limit_is_accepted(self):
        profile = SchoolProfile.get()
        profile.comment_max_length = 20
        profile.save()
        save_class_comment(self.ada, self.term, 'x' * 20, self.ct)
        self.assertTrue(ReportComment.objects.exists())


class CommentAuditTests(CommentSetup):
    def test_new_comment_is_logged(self):
        comment = save_class_comment(self.ada, self.term, 'Logged.', self.ct)
        self.assertTrue(AuditLog.objects.filter(
            model_name='report_cards.reportcomment', action='create', object_id=str(comment.pk),
        ).exists())

    def test_changed_comment_logs_the_old_and_new_text(self):
        save_class_comment(self.ada, self.term, 'Before.', self.ct)
        save_class_comment(self.ada, self.term, 'After.', self.ct)
        entry = AuditLog.objects.filter(
            model_name='report_cards.reportcomment', action='update',
        ).latest('pk')
        self.assertEqual(entry.changes['text'], ['Before.', 'After.'])

    def test_comments_cannot_be_deleted(self):
        comment = save_class_comment(self.ada, self.term, 'Keep me.', self.ct)
        with self.assertRaises(PermissionError):
            comment.delete()