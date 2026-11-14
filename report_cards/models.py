from django.conf import settings
from django.db import models

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