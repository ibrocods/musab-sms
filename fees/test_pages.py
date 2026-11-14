from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from core.models import SchoolClass, Student, Term
from fees.models import Discount, FeeItem, Payment


class PageSetup(TestCase):
    def setUp(self):
        call_command('sync_roles', verbosity=0)
        self.pw = 'pass12345!'
        self.term = Term.objects.create(
            session='2026/2027', term_number=1, name='First Term',
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15), is_current=True,
        )
        self.jss1a = SchoolClass.objects.create(name='JSS1A')
        self.ada = Student.objects.create(first_name='Ada', last_name='Obi', school_class=self.jss1a)
        self.tuition = FeeItem.objects.create(name='Tuition', amount=Decimal('50000'), term=self.term)

        self.bursar = self.make_user('bursar_pg', 'Bursar')
        self.head = self.make_user('head_pg', 'Head teacher')
        self.teacher = self.make_user('ct_pg', 'Class teacher')

    def make_user(self, username, role):
        user = User.objects.create_user(username, password=self.pw)
        user.groups.add(Group.objects.get(name=role))
        return user

    def login(self, user):
        client = Client()
        client.login(username=user.username, password=self.pw)
        return client

    def with_term(self, url):
        return f'{url}?term={self.term.pk}'

    def statement_url(self):
        return self.with_term(reverse('fees:statement', args=[self.ada.pk]))

    def pay_via_page(self, amount='20000'):
        url = self.with_term(reverse('fees:payment_record', args=[self.ada.pk]))
        return self.login(self.bursar).post(url, {
            'amount': amount, 'method': 'cash', 'paid_on': '2026-10-05',
            'reference': '', 'note': '',
        })


class StatementAccessTests(PageSetup):
    def test_bursar_can_open_the_statement(self):
        response = self.login(self.bursar).get(self.statement_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['row']['balance'], Decimal('50000.00'))

    def test_head_teacher_can_view_the_statement(self):
        response = self.login(self.head).get(self.statement_url())
        self.assertEqual(response.status_code, 200)

    def test_class_teacher_cannot_open_the_statement(self):
        response = self.login(self.teacher).get(self.statement_url())
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_sent_to_login(self):
        response = Client().get(self.statement_url())
        self.assertEqual(response.status_code, 302)


class PaymentPageTests(PageSetup):
    def test_bursar_records_a_payment(self):
        response = self.pay_via_page('20000')
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal('20000.00'))
        self.assertTrue(payment.receipt_number.startswith('RCPT-2026'))

    def test_head_teacher_cannot_record_a_payment(self):
        url = self.with_term(reverse('fees:payment_record', args=[self.ada.pk]))
        response = self.login(self.head).post(url, {
            'amount': '100', 'method': 'cash', 'paid_on': '2026-10-05',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_invalid_amount_saves_nothing(self):
        response = self.pay_via_page('0')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Payment.objects.exists())

    def test_bursar_reverses_a_payment(self):
        self.pay_via_page('20000')
        payment = Payment.objects.get()
        url = reverse('fees:payment_reverse', args=[payment.pk])
        response = self.login(self.bursar).post(url, {'reason': 'Entered twice'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Payment.objects.filter(kind='reversal', reverses=payment).exists())

    def test_reversal_needs_a_reason(self):
        self.pay_via_page('20000')
        payment = Payment.objects.get()
        url = reverse('fees:payment_reverse', args=[payment.pk])
        self.login(self.bursar).post(url, {'reason': '   '})
        self.assertFalse(Payment.objects.filter(kind='reversal').exists())

    def test_head_teacher_can_reverse(self):
        self.pay_via_page('20000')
        payment = Payment.objects.get()
        url = reverse('fees:payment_reverse', args=[payment.pk])
        self.login(self.head).post(url, {'reason': 'Approved correction'})
        self.assertTrue(Payment.objects.filter(kind='reversal').exists())


class FeeSetupPageTests(PageSetup):
    def test_bursar_can_open_setup(self):
        response = self.login(self.bursar).get(self.with_term(reverse('fees:setup')))
        self.assertEqual(response.status_code, 200)

    def test_head_teacher_cannot_open_setup(self):
        response = self.login(self.head).get(self.with_term(reverse('fees:setup')))
        self.assertEqual(response.status_code, 403)

    def test_bursar_adds_a_fee(self):
        response = self.login(self.bursar).post(reverse('fees:fee_create'), {
            'name': 'PTA levy', 'amount': '5000', 'term': self.term.pk,
            'school_class': '', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(FeeItem.objects.filter(name='PTA levy', school_class__isnull=True).exists())

    def test_duplicate_fee_is_refused(self):
        response = self.login(self.bursar).post(reverse('fees:fee_create'), {
            'name': 'Tuition', 'amount': '1000', 'term': self.term.pk,
            'school_class': '', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FeeItem.objects.filter(name='Tuition').count(), 1)

    def test_bursar_deactivates_a_fee(self):
        url = reverse('fees:fee_toggle', args=[self.tuition.pk])
        self.login(self.bursar).post(url)
        self.tuition.refresh_from_db()
        self.assertFalse(self.tuition.is_active)

    def test_head_teacher_cannot_toggle_a_fee(self):
        url = reverse('fees:fee_toggle', args=[self.tuition.pk])
        response = self.login(self.head).post(url)
        self.assertEqual(response.status_code, 403)
        self.tuition.refresh_from_db()
        self.assertTrue(self.tuition.is_active)


class DiscountPageTests(PageSetup):
    def grant_url(self):
        return self.with_term(reverse('fees:discount_grant', args=[self.ada.pk]))

    def test_head_teacher_grants_a_discount(self):
        self.login(self.head).post(self.grant_url(), {
            'kind': 'percent', 'value': '10', 'reason': 'Scholarship',
            'starts_on': '2026-09-01', 'ends_on': '',
        })
        self.assertEqual(Discount.objects.count(), 1)

    def test_class_teacher_cannot_grant_a_discount(self):
        response = self.login(self.teacher).post(self.grant_url(), {
            'kind': 'percent', 'value': '10', 'reason': 'Trying',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Discount.objects.exists())

    def test_discount_without_a_reason_is_refused(self):
        self.login(self.head).post(self.grant_url(), {
            'kind': 'percent', 'value': '10', 'reason': '',
        })
        self.assertFalse(Discount.objects.exists())

    def test_discount_can_be_ended(self):
        self.login(self.head).post(self.grant_url(), {
            'kind': 'fixed', 'value': '5000', 'reason': 'Hardship',
            'starts_on': '2026-09-01',
        })
        discount = Discount.objects.get()
        url = reverse('fees:discount_end', args=[discount.pk])
        self.login(self.head).post(url)
        discount.refresh_from_db()
        self.assertIsNotNone(discount.ends_on)


class DebtorsPageTests(PageSetup):
    def test_bursar_sees_debtors(self):
        response = self.login(self.bursar).get(self.with_term(reverse('fees:debtors')))
        self.assertEqual(response.status_code, 200)
        owing = [row['student'] for row in response.context['rows']]
        self.assertIn(self.ada, owing)

    def test_class_teacher_cannot_see_debtors(self):
        response = self.login(self.teacher).get(self.with_term(reverse('fees:debtors')))
        self.assertEqual(response.status_code, 403)

    def test_index_search_finds_a_student(self):
        response = self.login(self.bursar).get(reverse('fees:index'), {'q': 'Obi'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.ada, list(response.context['results']))