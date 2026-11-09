from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from .grading import grade_for
from .models import GradeBand


class GradeBandTests(TestCase):
    def test_default_bands_are_seeded(self):
        self.assertEqual(GradeBand.objects.count(), 6)

    def test_exact_cut_offs_earn_the_higher_grade(self):
        self.assertEqual(grade_for(70).grade, 'A')
        self.assertEqual(grade_for(60).grade, 'B')
        self.assertEqual(grade_for(45).grade, 'D')

    def test_just_below_a_cut_off_drops_a_grade(self):
        self.assertEqual(grade_for(69.99).grade, 'B')
        self.assertEqual(grade_for(44.99).grade, 'E')

    def test_extremes(self):
        self.assertEqual(grade_for(0).grade, 'F')
        self.assertEqual(grade_for(100).grade, 'A')

    def test_string_and_decimal_scores(self):
        self.assertEqual(grade_for('45.00').grade, 'D')
        self.assertEqual(grade_for(Decimal('44.99')).grade, 'E')

    def test_out_of_range_is_refused(self):
        with self.assertRaises(ValueError):
            grade_for(101)
        with self.assertRaises(ValueError):
            grade_for(-1)

    def test_non_number_is_refused(self):
        with self.assertRaises(ValueError):
            grade_for('abc')

    def test_changing_a_band_changes_the_result(self):
        band = GradeBand.objects.get(grade='A')
        band.min_score = 75
        band.save()
        self.assertEqual(grade_for(72).grade, 'B')

    def test_two_bands_cannot_share_a_cut_off(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GradeBand.objects.create(grade='Z', remark='Clash', min_score=70)