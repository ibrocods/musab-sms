from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import SchoolClass, Student, Term


class FeeItem(models.Model):
    name = models.CharField(max_length=100, help_text='For example Tuition or PTA levy')
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Amount in naira',
    )
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='fee_items')
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, null=True, blank=True, related_name='fee_items',
        help_text='Leave blank to charge every class',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['term', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'term', 'school_class'], name='unique_fee_item_per_term_class',
            ),
        ]

    def __str__(self):
        target = self.school_class.name if self.school_class else 'all classes'
        return f'{self.name} ({target}, {self.term}): {self.amount}'

    def clean(self):
        # The database treats blank classes as different from each other, so check those here too
        if not self.name or not self.term_id:
            return
        clashes = FeeItem.objects.filter(
            name=self.name, term_id=self.term_id, school_class_id=self.school_class_id,
        )
        if self.pk:
            clashes = clashes.exclude(pk=self.pk)
        if clashes.exists():
            raise ValidationError('A fee with this name already exists for this term and class.')


class Payment(models.Model):
    KIND_CHOICES = [('payment', 'Payment'), ('reversal', 'Reversal')]
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('transfer', 'Bank transfer'),
        ('pos', 'POS or card'),
        ('other', 'Other'),
    ]

    receipt_number = models.CharField(max_length=60, unique=True, editable=False, blank=True)
    receipt_year = models.PositiveIntegerField(editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='payments')
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name='payments')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='payment', editable=False)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text='Always a positive amount. A reversal has the same amount as the payment it cancels.',
    )
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=100, blank=True, help_text='Bank or POS reference')
    paid_on = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    reverses = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='reversal', editable=False,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name='+', editable=False,
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='payment_amount_positive'),
        ]

    def __str__(self):
        return f'{self.receipt_number} {self.student} {self.kind} {self.amount}'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Payments cannot be changed. Record a reversal instead.')
        if not self.receipt_number:
            from .receipts import next_receipt_number
            self.receipt_year = self.paid_on.year
            self.receipt_number = next_receipt_number(self.receipt_year)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Payments cannot be deleted. Record a reversal instead.')