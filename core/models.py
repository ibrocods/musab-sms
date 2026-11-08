from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from .capabilities import CAPABILITIES


class SchoolProfile(models.Model):
    name = models.CharField(max_length=200, default='My School')
    motto = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    primary_colour = models.CharField(
        max_length=7, default='#1F4E78',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use a hex colour such as #1F4E78.')],
        help_text='Hex colour, for example #1F4E78',
    )
    accent_colour = models.CharField(
        max_length=7, default='#F2A900',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use a hex colour such as #F2A900.')],
        help_text='Hex colour, for example #F2A900',
    )
    student_id_pattern = models.CharField(
        max_length=100, default='{year}/{seq:04d}',
        help_text='Example: {year}/{seq:04d} gives 2026/0001',
    )

    class Meta:
        verbose_name = 'School profile'
        # Django stores each capability as a permission. They're attached to this
        # model because it always exists, so the permissions are always created.
        permissions = list(CAPABILITIES.items())

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Only one profile is allowed per installation
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        profile, _ = cls.objects.get_or_create(pk=1)
        return profile


class TemporaryGrant(models.Model):
    """One capability given to one person for a fixed period, outside their role."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='temporary_grants',
    )
    capability = models.CharField(max_length=50, choices=list(CAPABILITIES.items()))
    reason = models.CharField(max_length=200, help_text='Why this is needed, for example "Bursar on leave"')
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='grants_given', editable=False,
    )
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(help_text='The grant stops working at this time')
    revoked_at = models.DateTimeField(null=True, blank=True, help_text='Set when the grant is removed early')

    class Meta:
        ordering = ['-starts_at']

    def __str__(self):
        return f'{self.user} - {self.capability}'

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError('The end date must be after the start date.')