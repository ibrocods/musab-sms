from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import Term
from core.permissions import require_capability
from core.scope import visible_students
from core.terms import current_term

from .balances import debtors, student_balance
from .discounts import end_discount, grant_discount
from .forms import DiscountForm, FeeItemForm, PaymentForm, ReversalForm
from .models import Discount, FeeItem, Payment
from .payments import record_payment, reverse_payment


def _term_from_request(request):
    pk = request.GET.get('term') or request.POST.get('term')
    if pk and str(pk).isdigit():
        term = Term.objects.filter(pk=pk).first()
        if term:
            return term
    return current_term()


def _with_term(url, term):
    return f'{url}?term={term.pk}' if term else url


def _statement_url(student, term):
    return _with_term(reverse('fees:statement', args=[student.pk]), term)


def _error_text(error):
    if isinstance(error, PermissionDenied):
        return 'You do not have permission to do that.'
    return ' '.join(error.messages)


@login_required
@require_capability('view_fees')
@require_GET
def index(request):
    q = request.GET.get('q', '').strip()
    results = []
    if q:
        results = (
            visible_students(request.user)
            .filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(student_id__icontains=q))
            .select_related('school_class')[:50]
        )
    return render(request, 'fees/index.html', {
        'q': q,
        'results': results,
        'term': _term_from_request(request),
        'terms': Term.objects.all(),
    })


@login_required
@require_capability('view_fees')
@require_GET
def statement(request, student_pk):
    student = get_object_or_404(visible_students(request.user).select_related('school_class'), pk=student_pk)
    term = _term_from_request(request)
    context = {'student': student, 'term': term, 'terms': Term.objects.all()}

    if term:
        today = timezone.localdate()
        context['row'] = student_balance(term, student)

        payments = []
        for payment in Payment.objects.filter(student=student, term=term):
            reversed_already = Payment.objects.filter(reverses=payment).exists()
            payments.append({
                'p': payment,
                'can_reverse': payment.kind == 'payment' and not reversed_already,
            })
        context['payments'] = payments

        discounts = []
        for discount in Discount.objects.filter(student=student, term=term):
            is_open = discount.ends_on is None or discount.ends_on >= today
            discounts.append({'d': discount, 'is_open': is_open})
        context['discounts'] = discounts

        context['payment_form'] = PaymentForm(initial={'paid_on': today})
        context['discount_form'] = DiscountForm(initial={'starts_on': today})
        context['reversal_form'] = ReversalForm()

    return render(request, 'fees/statement.html', context)


@login_required
@require_capability('collect_fees')
@require_POST
def payment_record(request, student_pk):
    student = get_object_or_404(visible_students(request.user), pk=student_pk)
    term = _term_from_request(request)

    if term is None:
        messages.error(request, 'No term is selected, and no current term is set.')
        return redirect(_statement_url(student, term))

    form = PaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Check the payment details and try again.')
        return redirect(_statement_url(student, term))

    try:
        payment = record_payment(student=student, term=term, user=request.user, **form.cleaned_data)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, f'Payment recorded. Receipt {payment.receipt_number}.')
    return redirect(_statement_url(student, term))


@login_required
@require_capability('reverse_payments')
@require_POST
def payment_reverse(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('student', 'term'), pk=pk)
    # Make sure this user is allowed to see the student before acting on the payment
    get_object_or_404(visible_students(request.user), pk=payment.student_id)

    form = ReversalForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Give a reason for the reversal.')
    else:
        try:
            reverse_payment(payment, user=request.user, reason=form.cleaned_data['reason'])
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, _error_text(error))
        else:
            messages.success(request, f'{payment.receipt_number} reversed. The reversal has its own receipt.')
    return redirect(_statement_url(payment.student, payment.term))


@login_required
@require_capability('grant_discounts')
@require_POST
def discount_grant(request, student_pk):
    student = get_object_or_404(visible_students(request.user), pk=student_pk)
    term = _term_from_request(request)

    if term is None:
        messages.error(request, 'No term is selected, and no current term is set.')
        return redirect(_statement_url(student, term))

    form = DiscountForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Check the discount details and try again.')
        return redirect(_statement_url(student, term))

    data = form.cleaned_data
    try:
        grant_discount(
            student=student, term=term, kind=data['kind'], value=data['value'],
            reason=data['reason'], user=request.user,
            starts_on=data['starts_on'], ends_on=data['ends_on'],
        )
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, 'Discount granted.')
    return redirect(_statement_url(student, term))


@login_required
@require_capability('grant_discounts')
@require_POST
def discount_end(request, pk):
    discount = get_object_or_404(Discount.objects.select_related('student', 'term'), pk=pk)
    get_object_or_404(visible_students(request.user), pk=discount.student_id)
    try:
        end_discount(discount, user=request.user)
    except PermissionDenied as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, 'Discount ended today. The record is kept.')
    return redirect(_statement_url(discount.student, discount.term))


@login_required
@require_capability('view_fees')
@require_GET
def debtors_list(request):
    term = _term_from_request(request)
    rows = []
    total = Decimal('0')
    if term:
        rows = debtors(term, visible_students(request.user).select_related('school_class'))
        total = sum((row['balance'] for row in rows), Decimal('0'))
    return render(request, 'fees/debtors.html', {
        'term': term,
        'terms': Term.objects.all(),
        'rows': rows,
        'total': total,
    })


@login_required
@require_capability('manage_fees')
@require_GET
def setup(request):
    term = _term_from_request(request)
    items = FeeItem.objects.select_related('school_class').filter(term=term) if term else FeeItem.objects.none()
    return render(request, 'fees/setup.html', {
        'term': term,
        'terms': Term.objects.all(),
        'items': items,
    })


@login_required
@require_capability('manage_fees')
def fee_create(request):
    term = _term_from_request(request)
    if request.method == 'POST':
        form = FeeItemForm(request.POST)
        if form.is_valid():
            fee = form.save()
            messages.success(request, 'Fee added.')
            return redirect(_with_term(reverse('fees:setup'), fee.term))
    else:
        form = FeeItemForm(initial={'term': term, 'is_active': True})
    return render(request, 'fees/fee_form.html', {'form': form, 'title': 'Add fee'})


@login_required
@require_capability('manage_fees')
@require_POST
def fee_toggle(request, pk):
    fee = get_object_or_404(FeeItem, pk=pk)
    fee.is_active = not fee.is_active
    fee.save()
    messages.success(request, f'{fee.name} is now {"active" if fee.is_active else "inactive"}.')
    return redirect(_with_term(reverse('fees:setup'), fee.term))