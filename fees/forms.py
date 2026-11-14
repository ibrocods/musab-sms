from decimal import Decimal

from django import forms

from .models import Discount, FeeItem, Payment


class StyledMixin:
    """Gives every field the right Bootstrap class."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')
            else:
                field.widget.attrs.setdefault('class', 'form-control')


class FeeItemForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = FeeItem
        fields = ['name', 'amount', 'term', 'school_class', 'is_active']


class PaymentForm(StyledMixin, forms.Form):
    amount = forms.DecimalField(min_value=Decimal('0.01'), max_digits=12, decimal_places=2)
    method = forms.ChoiceField(choices=Payment.METHOD_CHOICES)
    paid_on = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    reference = forms.CharField(max_length=100, required=False, label='Bank or POS reference')
    note = forms.CharField(max_length=200, required=False)


class ReversalForm(StyledMixin, forms.Form):
    reason = forms.CharField(max_length=200)


class DiscountForm(StyledMixin, forms.Form):
    kind = forms.ChoiceField(choices=Discount.KIND_CHOICES)
    value = forms.DecimalField(min_value=Decimal('0.01'), max_digits=12, decimal_places=2)
    reason = forms.CharField(max_length=200)
    starts_on = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ends_on = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))