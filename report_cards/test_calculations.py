from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import (
    Assessment, AttendanceRecord, ClassSubject, SchoolClass, Score, Student, Subject, Term,
)
from report_cards.calculations import class_results, subject_class_average, subject_result


class CalcSetup(TestCase):
    def setUp(self):
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
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.bola = Student.objects.create(first_name='Bola', last_name='Ade', school_class=self.jss1a)
        self.musa = Student.objects.create(first_name='Musa', last_name='Ali', school_class=self.jss1a)

    def enter(self, student, subject, test=None, exam=None):
        """Enter marks for a subject. Pass None to leave a mark out."""
        marks = {'Test': test, 'Exam': exam}
        for assessment in Assessment.objects.filter(subject=subject, term=self.term):
            value = marks[assessment.name]
            if value is not None:
                Score.objects.create(
                    student=student, assessment=assessment, score=Decimal(str(value)),
                )

    def results(self):
        return class_results(self.jss1a, self.term, [self.ada, self.bola, self.musa])

    def row(self, results, student):
        return next(r for r in results if r['student'] == student)

    def entry(self, row, subject):
        return next(s for s in row['subjects'] if s['subject'] == subject)


class SubjectTotalTests(CalcSetup):
    def test_total_uses_the_weights(self):
        self.enter(self.ada, self.maths, test=80, exam=50)  # 24 + 35
        result = subject_result(self.ada, self.maths_link, self.term)
        self.assertEqual(result['total'], Decimal('59.00'))
        self.assertEqual(result['grade'], 'C')
        self.assertTrue(result['complete'])

    def test_missing_mark_is_not_counted_as_zero(self):
        self.enter(self.bola, self.maths, test=80)
        result = subject_result(self.bola, self.maths_link, self.term)
        self.assertIsNone(result['total'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['missing'], ['Exam'])

    def test_weights_not_totalling_100_block_the_subject(self):
        Assessment.objects.filter(subject=self.maths, name='Exam').update(weight=60)
        self.enter(self.ada, self.maths, test=80, exam=50)
        result = subject_result(self.ada, self.maths_link, self.term)
        self.assertFalse(result['complete'])
        self.assertEqual(result['missing'], ['weights do not total 100'])

    def test_zero_maximum_is_refused(self):
        Assessment.objects.filter(subject=self.maths, name='Exam').update(max_mark=0)
        with self.assertRaises(ValueError):
            subject_result(self.ada, self.maths_link, self.term)


class PositionTests(CalcSetup):
    def test_tied_students_share_a_rank_and_the_next_rank_skips(self):
        chidi = Student.objects.create(first_name='Chidi', last_name='Eze', school_class=self.jss1a)
        self.enter(self.ada, self.maths, test=80, exam=50)    # 59
        self.enter(self.bola, self.maths, test=80, exam=50)   # 59
        self.enter(self.musa, self.maths, test=90, exam=70)   # 76
        self.enter(chidi, self.maths, test=40, exam=0)        # 12

        results = class_results(self.jss1a, self.term, [self.ada, self.bola, self.musa, chidi])
        self.assertEqual(self.entry(self.row(results, self.musa), self.maths)['position'], 1)
        self.assertEqual(self.entry(self.row(results, self.ada), self.maths)['position'], 2)
        self.assertEqual(self.entry(self.row(results, self.bola), self.maths)['position'], 2)
        self.assertEqual(self.entry(self.row(results, chidi), self.maths)['position'], 4)


class OverallTests(CalcSetup):
    def test_average_and_overall_position(self):
        self.enter(self.ada, self.maths, test=80, exam=50)        # 59
        self.enter(self.ada, self.english, test=100, exam=100)    # 100
        self.enter(self.musa, self.maths, test=90, exam=70)       # 76
        self.enter(self.musa, self.english, test=100, exam=100)   # 100
        self.enter(self.bola, self.maths, test=80, exam=50)       # 59
        self.enter(self.bola, self.english, test=50, exam=50)     # 50

        results = self.results()
        self.assertEqual(self.row(results, self.ada)['average'], Decimal('79.50'))
        self.assertEqual(self.row(results, self.musa)['average'], Decimal('88.00'))
        self.assertEqual(self.row(results, self.bola)['average'], Decimal('54.50'))
        self.assertEqual(self.row(results, self.musa)['position'], 1)
        self.assertEqual(self.row(results, self.ada)['position'], 2)
        self.assertEqual(self.row(results, self.bola)['position'], 3)

    def test_one_incomplete_subject_means_no_average_or_position(self):
        self.enter(self.ada, self.maths, test=80, exam=50)
        self.enter(self.ada, self.english, test=100, exam=100)
        self.enter(self.bola, self.maths, test=80, exam=50)
        self.enter(self.bola, self.english, test=50)  # English exam missing

        results = self.results()
        bola = self.row(results, self.bola)
        self.assertFalse(bola['complete'])
        self.assertIsNone(bola['average'])
        self.assertIsNone(bola['position'])
        self.assertEqual(self.row(results, self.ada)['position'], 1)


class ClassAverageTests(CalcSetup):
    def test_class_average_ignores_incomplete_results(self):
        self.enter(self.ada, self.maths, test=80, exam=50)   # 59
        self.enter(self.musa, self.maths, test=90, exam=70)  # 76
        self.enter(self.bola, self.maths, test=80)           # incomplete

        results = self.results()
        self.assertEqual(subject_class_average(results, self.maths), Decimal('67.50'))


class AttendanceInResultsTests(CalcSetup):
    def test_attendance_summary_is_attached(self):
        AttendanceRecord.objects.create(
            student=self.ada, school_class=self.jss1a, term=self.term,
            date=date(2026, 10, 5), status='P',
        )
        AttendanceRecord.objects.create(
            student=self.ada, school_class=self.jss1a, term=self.term,
            date=date(2026, 10, 6), status='A',
        )
        row = self.row(self.results(), self.ada)
        self.assertEqual(row['attendance']['marked'], 2)
        self.assertEqual(row['attendance']['percentage'], Decimal('50.0'))