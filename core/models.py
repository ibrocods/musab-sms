from django.db import models
from django.core.validators import RegexValidator

class SchoolProfile(models.Model):
    name = models.CharField(max_length=200, default='My School')
    motto = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    primary_colour = models.CharField(
        max_length=7, default='#1F4E78',
        help_text='Hex colour, for example #1F4E78',
    )
    accent_colour = models.CharField(
        max_length=7, default='#F2A900',
        help_text='Hex colour, for example #F2A900',
    )
    student_id_pattern = models.CharField(
        max_length=100, default='{year}/{seq:04d}',
        help_text='Example: {year}/{seq:04d} gives 2026/0001',
    )
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
    class Meta:
        verbose_name = 'School profile'

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