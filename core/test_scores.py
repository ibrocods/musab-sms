from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import Assessment, AuditLog, ClassSubject, SchoolClass, Score, Student, Subject, Term
from .scoring import can_enter_scores, grade_for_score, parse_score, save_score


class ScoreSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'

        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.english = Subject.objects.create(name='English', code='ENG')
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.jss2b = SchoolClass.objects.create(name='JSS2B')

        self.subject_teacher = self.make_user('maths1', 'Subject teacher')
        self.other_teacher = self.make_user('english1', 'Subject teacher')
        self.class_teacher = self.make_user('ct1', 'Class teacher')
        self.head = self.make_user('hd1', 'Head teacher')

        self.jss1a.class_teacher = self.class_teacher
        self.jss1a.save()

        self.maths_link = ClassSubject.objects.create(
            school_class=self.jss1a, subject=self.maths, teacher=self.subject_teacher,
        )
        ClassSubject.objects.create(
            school_class=self.jss1a, subject=self.english, teacher=self.other_teacher,
        )

        self.maths_exam = Assessment.objects.create(
            subject=self.maths, term=self.term, name='Exam', weight=100, max_mark=40,
        )
        self.english_exam = Assessment.objects.create(
            subject=self.english, term=self.term, name='Exam', weight=100, max_mark=40,
        )

        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.musa = Student.objects.create(first_name='Musa', last_name='Ali', school_class=self.jss2b)

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client


class ScoreRuleTests(ScoreSetup):
    def test_assigned_subject_teacher_can_enter(self):
        self.assertTrue(can_enter_scores(self.subject_teacher, self.maths_link))

    def test_unassigned_teacher_cannot_enter(self):
        self.assertFalse(can_enter_scores(self.other_teacher, self.maths_link))

    def test_class_teacher_can_enter_for_their_class(self):
        self.assertTrue(can_enter_scores(self.class_teacher, self.maths_link))

    def test_head_teacher_cannot_open_the_entry_page(self):
        url = reverse('score_entry', args=[self.maths_link.pk, self.maths_exam.pk])
        self.assertEqual(self.login(self.head).get(url).status_code, 403)


class ScoreValueTests(ScoreSetup):
    def test_valid_mark_is_parsed(self):
        self.assertEqual(parse_score('35', 40), Decimal('35.00'))

    def test_blank_means_no_mark(self):
        self.assertIsNone(parse_score('', 40))

    def test_mark_above_maximum_is_refused(self):
        with self.assertRaises(ValidationError):
            parse_score('41', 40)

    def test_negative_mark_is_refused(self):
        with self.assertRaises(ValidationError):
            parse_score('-1', 40)

    def test_non_number_is_refused(self):
        with self.assertRaises(ValidationError):
            parse_score('abc', 40)

    def test_grade_follows_the_percentage(self):
        save_score(self.ada, self.maths_exam, Decimal('35'), self.subject_teacher)
        score = Score.objects.get(student=self.ada, assessment=self.maths_exam)
        self.assertEqual(grade_for_score(score).grade, 'A')  # 35 of 40 is 87.5%

    def test_saving_twice_updates_one_row(self):
        save_score(self.ada, self.maths_exam, Decimal('20'), self.subject_teacher)
        save_score(self.ada, self.maths_exam, Decimal('30'), self.subject_teacher)
        self.assertEqual(Score.objects.count(), 1)
        self.assertEqual(Score.objects.get().score, Decimal('30'))

    def test_blank_removes_the_mark(self):
        save_score(self.ada, self.maths_exam, Decimal('20'), self.subject_teacher)
        save_score(self.ada, self.maths_exam, None, self.subject_teacher)
        self.assertFalse(Score.objects.exists())

    def test_changing_a_mark_is_logged(self):
        save_score(self.ada, self.maths_exam, Decimal('20'), self.subject_teacher)
        save_score(self.ada, self.maths_exam, Decimal('30'), self.subject_teacher)
        self.assertTrue(AuditLog.objects.filter(
            model_name='core.score', action='update',
        ).exists())


class ScoreViewTests(ScoreSetup):
    def entry_url(self, class_subject, assessment):
        return reverse('score_entry', args=[class_subject.pk, assessment.pk])

    def test_subject_teacher_saves_marks_for_their_class(self):
        response = self.login(self.subject_teacher).post(
            self.entry_url(self.maths_link, self.maths_exam),
            {f'score_{self.ada.pk}': '35'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Score.objects.get(student=self.ada).score, Decimal('35.00'))

    def test_marks_for_students_in_other_classes_are_ignored(self):
        self.login(self.subject_teacher).post(
            self.entry_url(self.maths_link, self.maths_exam),
            {f'score_{self.musa.pk}': '30'},
        )
        self.assertFalse(Score.objects.filter(student=self.musa).exists())

    def test_invalid_mark_saves_nothing(self):
        response = self.login(self.subject_teacher).post(
            self.entry_url(self.maths_link, self.maths_exam),
            {f'score_{self.ada.pk}': '50'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Score.objects.exists())

    def test_assessment_from_another_subject_is_not_found(self):
        url = self.entry_url(self.maths_link, self.english_exam)
        self.assertEqual(self.login(self.subject_teacher).get(url).status_code, 404)

    def test_unassigned_teacher_is_refused(self):
        url = self.entry_url(self.maths_link, self.maths_exam)
        self.assertEqual(self.login(self.other_teacher).get(url).status_code, 403)

    def test_index_shows_only_the_teachers_own_subjects(self):
        response = self.login(self.subject_teacher).get(reverse('score_index'))
        entries = response.context['entries']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['class_subject'], self.maths_link)