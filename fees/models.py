from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import SchoolClass, Term


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