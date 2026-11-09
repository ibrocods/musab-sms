from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from django.contrib.auth.models import Group, User

from .assessments import check_weights
from .models import Assessment, ClassSubject, SchoolClass, Subject, Term


class SubjectSetup(TestCase):
    def setUp(self):
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        self.maths = Subject.objects.create(name='Mathematics', code='MTH')
        self.english = Subject.objects.create(name='English', code='ENG')


class SubjectTests(SubjectSetup):
    def test_subject_names_are_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(name='Mathematics')


class ClassSubjectTests(SubjectSetup):
    def test_class_cannot_have_a_subject_twice(self):
        school_class = SchoolClass.objects.create(name='JSS1A')
        ClassSubject.objects.create(school_class=school_class, subject=self.maths)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClassSubject.objects.create(school_class=school_class, subject=self.maths)

    def test_teacher_can_be_assigned_to_a_class_subject(self):
        school_class = SchoolClass.objects.create(name='JSS1A')
        teacher = User.objects.create_user('maths1', password='pass12345!')
        teacher.groups.add(Group.objects.get_or_create(name='Subject teacher')[0])
        link = ClassSubject.objects.create(school_class=school_class, subject=self.maths, teacher=teacher)
        self.assertEqual(link.teacher, teacher)


class WeightTests(SubjectSetup):
    def test_weights_totalling_100_pass(self):
        Assessment.objects.create(subject=self.maths, term=self.term, name='Test', weight=30)
        Assessment.objects.create(subject=self.maths, term=self.term, name='Exam', weight=70)
        check_weights(self.maths, self.term)  # should not raise

    def test_weights_not_totalling_100_are_flagged(self):
        Assessment.objects.create(subject=self.maths, term=self.term, name='Test', weight=30)
        with self.assertRaises(ValidationError):
            check_weights(self.maths, self.term)

    def test_weights_are_checked_per_subject(self):
        Assessment.objects.create(subject=self.maths, term=self.term, name='Test', weight=100)
        Assessment.objects.create(subject=self.english, term=self.term, name='Test', weight=40)
        check_weights(self.maths, self.term)  # maths is fine
        with self.assertRaises(ValidationError):
            check_weights(self.english, self.term)

    def test_weights_are_checked_per_term(self):
        second = Term.objects.create(
            session='2026/2027', term_number=2, name='Second Term',
            start_date=date(2027, 1, 10), end_date=date(2027, 4, 5),
        )
        Assessment.objects.create(subject=self.maths, term=self.term, name='Exam', weight=100)
        Assessment.objects.create(subject=self.maths, term=second, name='Exam', weight=50)
        check_weights(self.maths, self.term)  # first term fine
        with self.assertRaises(ValidationError):
            check_weights(self.maths, second)

    def test_same_assessment_name_twice_in_a_term_is_refused(self):
        Assessment.objects.create(subject=self.maths, term=self.term, name='Test', weight=30)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assessment.objects.create(subject=self.maths, term=self.term, name='Test', weight=20)

    def test_negative_or_oversized_weight_is_refused(self):
        bad = Assessment(subject=self.maths, term=self.term, name='Bad', weight=150)
        with self.assertRaises(ValidationError):
            bad.full_clean()