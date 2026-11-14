from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import AuditLog, SchoolClass, Term
from fees.models import FeeItem


class FeeSetup(TestCase):
    def setUp(self):
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.second_term = Term.objects.create(
            session='2026/2027', term_number=2, name='Second Term',
            start_date=date(2027, 1, 10), end_date=date(2027, 4, 5),
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')


class FeeItemTests(FeeSetup):
    def test_blank_class_means_every_class(self):
        fee = FeeItem.objects.create(name='PTA levy', amount=Decimal('5000'), term=self.term)
        self.assertIsNone(fee.school_class)

    def test_negative_amount_is_refused(self):
        fee = FeeItem(name='Bad', amount=Decimal('-1'), term=self.term)
        with self.assertRaises(ValidationError):
            fee.full_clean()

    def test_same_name_for_one_class_is_refused(self):
        FeeItem.objects.create(
            name='Tuition', amount=Decimal('50000'), term=self.term, school_class=self.jss1a,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            FeeItem.objects.create(
                name='Tuition', amount=Decimal('40000'), term=self.term, school_class=self.jss1a,
            )

    def test_same_name_for_every_class_is_refused(self):
        FeeItem.objects.create(name='PTA levy', amount=Decimal('5000'), term=self.term)
        duplicate = FeeItem(name='PTA levy', amount=Decimal('6000'), term=self.term)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_same_name_in_another_term_is_allowed(self):
        FeeItem.objects.create(name='Tuition', amount=Decimal('50000'), term=self.term)
        FeeItem.objects.create(name='Tuition', amount=Decimal('50000'), term=self.second_term)
        self.assertEqual(FeeItem.objects.filter(name='Tuition').count(), 2)

    def test_changing_an_amount_is_logged(self):
        fee = FeeItem.objects.create(name='Tuition', amount=Decimal('50000'), term=self.term)
        fee.amount = Decimal('55000')
        fee.save()
        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.feeitem', action='update', object_id=str(fee.pk),
        ).exists())

    def test_creating_an_item_is_logged(self):
        fee = FeeItem.objects.create(name='Tuition', amount=Decimal('50000'), term=self.term)
        self.assertTrue(AuditLog.objects.filter(
            model_name='fees.feeitem', action='create', object_id=str(fee.pk),
        ).exists())