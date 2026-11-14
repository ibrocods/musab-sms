from django.conf import settings
from django.db import models
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from core.models import Student, Term


class ReportComment(models.Model):
    KIND_CHOICES = [
        ('class_teacher', 'Class teacher comment'),
        ('head_teacher', 'Head teacher remark'),
    ]

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='report_comments')
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name='report_comments')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    text = models.TextField(blank=True)
    written_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['student', 'kind']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'term', 'kind'], name='unique_comment_per_kind',
            ),
        ]

    def __str__(self):
        return f'{self.student} {self.term} {self.get_kind_display()}'

    def delete(self, *args, **kwargs):
        raise PermissionError('Comments cannot be deleted. Replace the text instead.')


class ReportCard(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('approved', 'Approved')]

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='report_cards')
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name='report_cards')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', editable=False)
    snapshot = models.JSONField(
        null=True, blank=True, editable=False,
        help_text='Results frozen at the moment of approval',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', editable=False,
    )
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    reopen_reason = models.CharField(max_length=200, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Set only by freeze() and reopen(), so ordinary saves can't bypass the lock
    _permitted_change = False

    class Meta:
        ordering = ['student__last_name', 'student__first_name']
        constraints = [
            models.UniqueConstraint(fields=['student', 'term'], name='unique_report_card_per_term'),
        ]

    def __str__(self):
        return f'{self.student} {self.term} ({self.get_status_display()})'

    @property
    def is_frozen(self):
        return self.status == 'approved'

    def save(self, *args, **kwargs):
        if self.pk and not self._permitted_change and self._frozen_in_database():
            raise PermissionError('This report card is approved and frozen. Reopen it with a reason first.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Report cards cannot be deleted.')

    def _frozen_in_database(self):
        return ReportCard.objects.filter(pk=self.pk, status='approved').exists()

    def _save_as_permitted(self):
        self._permitted_change = True
        try:
            self.save()
        finally:
            self._permitted_change = False

    def freeze(self, snapshot, user):
        """Approve the card and store the results as they stand now."""
        if self.status == 'approved':
            raise ValidationError('This report card is already approved.')
        self.snapshot = snapshot
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        self._save_as_permitted()

    def reopen(self, reason):
        """Return an approved card to draft so it can be corrected and approved again.

        The old snapshot is cleared. The audit log keeps the record of what was approved.
        """
        reason = (reason or '').strip()
        if not reason:
            raise ValidationError('Give a reason for reopening the report card.')
        if self.status != 'approved':
            raise ValidationError('Only an approved report card can be reopened.')
        self.status = 'draft'
        self.snapshot = None
        self.approved_by = None
        self.approved_at = None
        self.reopen_reason = reason[:200]
        self._save_as_permitted()